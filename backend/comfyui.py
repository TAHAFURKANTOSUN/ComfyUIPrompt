"""ComfyUI entegrasyonu (Faz 2 — opsiyonel).

Hazır text2img workflow şablonuna (CheckpointLoader -> CLIPTextEncode x2 ->
KSampler -> VAEDecode -> SaveImage) üretilen prompt ve ayarları enjekte edip
ComfyUI'nin /prompt endpoint'ine gönderir. İstekler backend üzerinden proxy'lenir,
böylece tarayıcıda CORS sorunu yaşanmaz.

Not: LoRA'lı üretimde kullanıcı kendi workflow'una LoraLoader eklemelidir;
bu basit şablon LoRA node'u içermez (README'de açıklanır).
"""
import json
import random
from pathlib import Path

import httpx

WORKFLOW_PATH = Path(__file__).resolve().parent / "workflows" / "text2img_checkpoint.json"

CLIENT_ID = "comfyui-prompt-asistani"


class ComfyError(Exception):
    def __init__(self, message: str, hint: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint


def _norm_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ComfyError("ComfyUI adresi boş.", "Ör. http://127.0.0.1:8188")
    if not url.startswith(("http://", "https://")):
        url = "http://" + url
    return url


def _net_error(url: str, exc: Exception) -> ComfyError:
    if isinstance(exc, httpx.TimeoutException):
        return ComfyError(
            f"ComfyUI yanıt vermedi ({url}).",
            "ComfyUI meşgul olabilir (model yükleniyor); birkaç saniye sonra tekrar deneyin.",
        )
    if isinstance(exc, httpx.ConnectError):
        return ComfyError(
            f"ComfyUI'ye ulaşılamıyor ({url}).",
            "ComfyUI'nin açık olduğundan ve adresin doğru olduğundan emin olun.",
        )
    return ComfyError(f"ComfyUI isteği ağ hatasıyla kesildi: {str(exc)[:200]}")


async def list_checkpoints(url: str) -> list:
    url = _norm_url(url)
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(10.0, connect=4.0)) as client:
            resp = await client.get(f"{url}/object_info/CheckpointLoaderSimple")
    except httpx.HTTPError as exc:
        raise _net_error(url, exc)
    if resp.status_code >= 400:
        raise ComfyError(
            f"ComfyUI isteği başarısız oldu (HTTP {resp.status_code}).",
            "Adresin bir ComfyUI sunucusuna ait olduğundan emin olun (varsayılan port 8188).",
        )
    try:
        names = resp.json()["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except (KeyError, IndexError, TypeError, ValueError):
        raise ComfyError("ComfyUI beklenmeyen bir yanıt döndürdü (checkpoint listesi okunamadı).")
    if not isinstance(names, list):
        raise ComfyError("ComfyUI beklenmeyen bir yanıt döndürdü (checkpoint listesi okunamadı).")
    return [str(n) for n in names]


async def send(url: str, req: dict) -> dict:
    """req: {checkpoint, positive, negative, width, height, steps, cfg, sampler, scheduler, seed?}"""
    url = _norm_url(url)
    wf = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))

    wf["4"]["inputs"]["ckpt_name"] = req["checkpoint"]
    wf["5"]["inputs"]["width"] = int(req["width"])
    wf["5"]["inputs"]["height"] = int(req["height"])
    wf["6"]["inputs"]["text"] = req.get("positive") or ""
    wf["7"]["inputs"]["text"] = req.get("negative") or ""
    ks = wf["3"]["inputs"]
    # seed=0 geçerli bir değerdir; yalnızca hiç verilmediyse rastgele seç.
    seed = req.get("seed")
    ks["seed"] = int(seed) if seed is not None else random.randint(0, 2**48)
    ks["steps"] = int(req.get("steps") or 28)
    ks["cfg"] = float(req.get("cfg") or 6.0)
    ks["sampler_name"] = req.get("sampler") or "dpmpp_2m"
    ks["scheduler"] = req.get("scheduler") or "karras"

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(20.0, connect=4.0)) as client:
            resp = await client.post(
                f"{url}/prompt", json={"prompt": wf, "client_id": CLIENT_ID}
            )
    except httpx.HTTPError as exc:
        raise _net_error(url, exc)
    if resp.status_code >= 400:
        detail = resp.text[:400]
        hint = None
        if "sampler_name" in detail:
            hint = "Seçili sampler bu ComfyUI sürümünde yok olabilir."
        elif "ckpt_name" in detail:
            hint = "Checkpoint adı sunucudakiyle eşleşmiyor; listeden yeniden seçin."
        raise ComfyError(f"ComfyUI isteği reddetti: {detail}", hint)
    try:
        data = resp.json()
    except ValueError:
        data = {}
    return {"ok": True, "prompt_id": data.get("prompt_id") if isinstance(data, dict) else None, "seed": ks["seed"]}
