"""Yerel LLM istemcisi.

İki mod desteklenir (config.json -> llm.mode):
  - "ollama": Ollama'nın kendi /api/chat endpoint'i. JSON şema kısıtlı çıktı
    (structured outputs) kullanılır; eski Ollama sürümlerinde şema desteklenmezse
    otomatik olarak format="json"a, o da olmazsa serbest metne düşer.
  - "openai": /v1/chat/completions (LM Studio, llama.cpp server, vLLM vb.).

Görselden prompt tahmini için ayrı bir çok-modlu model (llm.vision_model) kullanılır:
görsel önce bu modelle İngilizce bir tarife dönüştürülür, tarif normal metin boru
hattına verilir (iki aşamalı akış — bkz. NOTES.md).

API anahtarı gerekmez; her şey yereldir.
"""
import re

import httpx

_THINK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.S)

DEFAULT_VISION_MODEL = "qwen2.5vl:7b"

# Modelin döndürmesi gereken JSON'un şeması (Ollama structured outputs).
JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["chat", "generate"]},
        "message": {"type": "string"},
        "positive_prompt": {"type": "string"},
        "negative_prompt": {"type": ["string", "null"]},
        "lora": {
            "type": ["object", "null"],
            "properties": {
                "name": {"type": "string"},
                "trigger": {"type": "string"},
                "weight": {"type": "number"},
            },
        },
        "note": {"type": ["string", "null"]},
    },
    "required": ["action"],
}


class LLMError(Exception):
    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.hint = hint


def _merged(cfg_llm: dict, overrides: dict | None) -> dict:
    cfg = dict(cfg_llm)
    for key in ("model", "base_url", "mode", "vision_model"):
        if overrides and overrides.get(key):
            cfg[key] = overrides[key]
    cfg["base_url"] = (cfg.get("base_url") or "").strip().rstrip("/")
    if not cfg["base_url"]:
        raise LLMError("bad_config", "LLM sunucu adresi (base_url) boş.", "Ayarlar'dan veya config.json'dan adresi girin.")
    return cfg


def _json(resp: httpx.Response) -> dict:
    """Yanıtı JSON olarak çözer; JSON değilse anlaşılır bir LLMError fırlatır."""
    try:
        data = resp.json()
    except ValueError:
        raise LLMError("llm_error", f"LLM sunucusu JSON olmayan bir yanıt döndürdü: {resp.text[:200]}")
    if not isinstance(data, dict):
        raise LLMError("llm_error", f"Beklenmeyen yanıt biçimi: {str(data)[:200]}")
    return data


def _net_error(cfg: dict, exc: Exception, what: str = "LLM") -> LLMError:
    """httpx ağ hatalarını kullanıcıya gösterilecek LLMError'a çevirir."""
    if isinstance(exc, httpx.TimeoutException):
        return LLMError(
            "timeout",
            f"{what} yanıtı zaman aşımına uğradı.",
            "Daha küçük bir model deneyin (ör. qwen3:8b) veya config.json'da timeout_s değerini artırın.",
        )
    if isinstance(exc, httpx.ConnectError):
        if cfg.get("mode") == "openai":
            return LLMError(
                "unreachable",
                f"LLM sunucusuna ulaşılamıyor ({cfg['base_url']}).",
                "Sunucunun (LM Studio / llama.cpp / Ollama) çalıştığından emin olun.",
            )
        return LLMError(
            "unreachable",
            f"Ollama'ya ulaşılamıyor ({cfg['base_url']}).",
            "Ollama'nın kurulu ve çalışır olduğundan emin olun: `ollama serve`",
        )
    return LLMError("llm_error", f"{what} isteği ağ hatasıyla kesildi: {str(exc)[:200]}")


def _model_matches(wanted: str, installed: list) -> bool:
    """Ollama etiket kuralı: 'qwen3' == 'qwen3:latest'. Farklı boyut etiketi
    (qwen3:8b vs qwen3:14b) eşleşme SAYILMAZ — aksi halde yüklü olmayan bir
    model 'yüklü' görünür ve ilk istekte 404 alınır."""
    def norm(name: str) -> str:
        name = (name or "").strip()
        return name if ":" in name.rsplit("/", 1)[-1] else f"{name}:latest"
    w = norm(wanted)
    return any(norm(m) == w for m in installed)


def _timeout(cfg: dict) -> httpx.Timeout:
    return httpx.Timeout(float(cfg.get("timeout_s", 300)), connect=5.0)


async def chat(cfg_llm: dict, messages: list, overrides: dict | None = None) -> str:
    """Mesaj listesini yerel LLM'e gönderir, ham metin yanıtını döndürür."""
    cfg = _merged(cfg_llm, overrides)
    if cfg.get("mode") == "openai":
        return await _chat_openai(cfg, messages)
    return await _chat_ollama(cfg, messages)


async def _chat_ollama(cfg: dict, messages: list) -> str:
    url = f"{cfg['base_url']}/api/chat"
    base_payload = {
        "model": cfg["model"],
        "messages": messages,
        "stream": False,
        "options": {"temperature": cfg.get("temperature", 0.7)},
        "keep_alive": cfg.get("keep_alive", "5m"),
    }
    async with httpx.AsyncClient(trust_env=False, timeout=_timeout(cfg)) as client:
        last_err = None
        # Şema kısıtlı -> düz JSON modu -> serbest metin sırasıyla dene
        # (eski Ollama sürümleriyle uyumluluk için kademeli düşüş).
        for fmt in (JSON_SCHEMA, "json", None):
            payload = dict(base_payload)
            if fmt is not None:
                payload["format"] = fmt
            try:
                resp = await client.post(url, json=payload)
            except httpx.HTTPError as exc:
                raise _net_error(cfg, exc)
            if resp.status_code < 400:
                data = _json(resp)
                return (data.get("message") or {}).get("content", "") or data.get("response", "")
            body = resp.text
            if resp.status_code == 404 or "not found" in body.lower():
                raise LLMError(
                    "model_not_found",
                    f"'{cfg['model']}' modeli Ollama'da yüklü değil.",
                    f"Şu komutla indirin: `ollama pull {cfg['model']}`",
                )
            last_err = f"HTTP {resp.status_code}: {body[:300]}"
            if resp.status_code >= 500 and "format" not in body.lower():
                # Sunucu tarafı hata (ör. bellek yetersiz) — format düşüşüyle düzelmez,
                # aynı ağır isteği 3 kez tekrarlamanın anlamı yok.
                break
            # format parametresi desteklenmiyor olabilir -> bir sonraki moda düş
        raise LLMError("llm_error", f"LLM isteği başarısız oldu. {last_err}")


async def _chat_openai(cfg: dict, messages: list) -> str:
    url = f"{cfg['base_url']}/v1/chat/completions"
    payload = {
        "model": cfg["model"],
        "messages": messages,
        "temperature": cfg.get("temperature", 0.7),
        "stream": False,
    }
    async with httpx.AsyncClient(trust_env=False, timeout=_timeout(cfg)) as client:
        for use_rf in (True, False):
            body = dict(payload)
            if use_rf:
                body["response_format"] = {"type": "json_object"}
            try:
                resp = await client.post(url, json=body)
            except httpx.HTTPError as exc:
                raise _net_error(cfg, exc)
            if resp.status_code < 400:
                data = _json(resp)
                try:
                    return data["choices"][0]["message"]["content"] or ""
                except (KeyError, IndexError, TypeError):
                    raise LLMError("llm_error", f"Beklenmeyen yanıt biçimi: {str(data)[:300]}")
            if resp.status_code == 404:
                raise LLMError(
                    "model_not_found",
                    f"'{cfg['model']}' modeli sunucuda bulunamadı (veya uç nokta yok).",
                    "Sunucuda yüklü model adını Ayarlar'dan seçin.",
                )
            if not use_rf:
                raise LLMError("llm_error", f"HTTP {resp.status_code}: {resp.text[:300]}")
        raise LLMError("llm_error", "LLM isteği başarısız oldu.")


async def describe_image(
    cfg_llm: dict,
    image_b64: str,
    instruction: str,
    overrides: dict | None = None,
    mime: str = "image/jpeg",
) -> str:
    """Görseli çok-modlu (vision) modelle ayrıntılı İngilizce tarife çevirir.
    Dönen tarif, normal sohbet boru hattına kullanıcı mesajı içinde verilir."""
    cfg = _merged(cfg_llm, overrides)
    model = cfg.get("vision_model") or DEFAULT_VISION_MODEL

    if cfg.get("mode") == "openai":
        url = f"{cfg['base_url']}/v1/chat/completions"
        payload = {
            "model": model,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": instruction},
                    {"type": "image_url",
                     "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
                ],
            }],
            "temperature": 0.3,
            "stream": False,
        }
    else:
        url = f"{cfg['base_url']}/api/chat"
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": instruction, "images": [image_b64]}],
            "stream": False,
            "options": {"temperature": 0.3},
            "keep_alive": cfg.get("keep_alive", "5m"),
        }

    async with httpx.AsyncClient(trust_env=False, timeout=_timeout(cfg)) as client:
        try:
            resp = await client.post(url, json=payload)
        except httpx.TimeoutException:
            raise LLMError(
                "timeout",
                "Görsel analizi zaman aşımına uğradı.",
                "Daha küçük bir vision modeli deneyin (ör. qwen2.5vl:3b).",
            )
        except httpx.HTTPError as exc:
            raise _net_error(cfg, exc, "Görsel analizi")

    if resp.status_code >= 400:
        body = resp.text
        if resp.status_code == 404 or "not found" in body.lower():
            raise LLMError(
                "vision_model_not_found",
                f"Görsel analizi için '{model}' modeli yüklü değil.",
                f"Şu komutla indirin: `ollama pull {model}` (veya Ayarlar'dan farklı bir vision modeli seçin).",
            )
        if "image" in body.lower() and "support" in body.lower():
            raise LLMError(
                "no_vision_support",
                f"'{model}' modeli görsel girdisini desteklemiyor.",
                "Ayarlar'dan çok-modlu bir model seçin (ör. qwen2.5vl:7b, gemma3:4b).",
            )
        raise LLMError("llm_error", f"Görsel analizi başarısız: HTTP {resp.status_code}: {body[:300]}")

    data = _json(resp)
    if cfg.get("mode") == "openai":
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            text = ""
    else:
        text = (data.get("message") or {}).get("content", "") or data.get("response", "")
    text = _THINK_RE.sub("", text).strip()
    if not text:
        raise LLMError("vision_empty", "Görsel modeli boş yanıt döndürdü; tekrar deneyin.")
    return text


async def status(cfg_llm: dict, overrides: dict | None = None) -> dict:
    """Sunucu erişilebilir mi + yüklü modeller."""
    try:
        cfg = _merged(cfg_llm, overrides)
    except LLMError as exc:
        return {"ok": False, "mode": cfg_llm.get("mode", "ollama"), "base_url": "",
                "configured_model": cfg_llm.get("model"), "models": [], "model_available": False,
                "vision_model": cfg_llm.get("vision_model") or DEFAULT_VISION_MODEL,
                "vision_available": False, "error": exc.message}
    result = {
        "ok": False,
        "mode": cfg.get("mode", "ollama"),
        "base_url": cfg["base_url"],
        "configured_model": cfg["model"],
        "models": [],
        "model_available": False,
        "vision_model": cfg.get("vision_model") or DEFAULT_VISION_MODEL,
        "vision_available": False,
        "error": None,
    }
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(6.0, connect=3.0)) as client:
            if cfg.get("mode") == "openai":
                resp = await client.get(f"{cfg['base_url']}/v1/models")
                resp.raise_for_status()
                result["models"] = [m.get("id", "") for m in resp.json().get("data", [])]
            else:
                resp = await client.get(f"{cfg['base_url']}/api/tags")
                resp.raise_for_status()
                result["models"] = [m.get("name", "") for m in resp.json().get("models", [])]
        result["ok"] = True
        result["model_available"] = _model_matches(cfg["model"], result["models"])
        result["vision_available"] = _model_matches(result["vision_model"], result["models"])
    except Exception as exc:
        result["error"] = str(exc)[:200]
    return result


async def unload(cfg_llm: dict, overrides: dict | None = None) -> dict:
    """Modeli bellekten boşaltır (VRAM'i ComfyUI'ye bırakmak için).
    Ollama'da keep_alive=0 ile boş bir istek göndermek modeli kaldırır."""
    try:
        cfg = _merged(cfg_llm, overrides)
    except LLMError as exc:
        return {"ok": False, "message": exc.message}
    if cfg.get("mode") == "openai":
        return {"ok": False, "message": "Bellek boşaltma yalnızca Ollama modunda destekleniyor."}
    targets = [cfg["model"]]
    if cfg.get("vision_model") and cfg["vision_model"] not in targets:
        targets.append(cfg["vision_model"])
    freed = []
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(15.0, connect=3.0)) as client:
            for model in targets:
                resp = await client.post(
                    f"{cfg['base_url']}/api/chat",
                    json={"model": model, "messages": [], "keep_alive": 0},
                )
                if resp.status_code < 400:
                    freed.append(model)
        if freed:
            return {"ok": True, "message": f"Bellekten boşaltıldı: {', '.join(freed)}."}
        return {"ok": False, "message": "Hiçbir model boşaltılamadı (yüklü olmayabilirler)."}
    except Exception as exc:
        return {"ok": False, "message": f"Ollama'ya ulaşılamadı: {str(exc)[:200]}"}
