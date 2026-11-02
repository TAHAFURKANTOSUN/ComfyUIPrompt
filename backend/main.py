"""ComfyUI Prompt Asistanı — FastAPI backend.

Çalıştırma (proje kökünden):
    python -m backend.main
veya:
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
"""
import asyncio
import base64
import binascii
import re
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import comfyui, llm_client, presets, prompting
from .sessions import get_store
from .config import ROOT, load_config

app = FastAPI(title="ComfyUI Prompt Asistanı")

# ---------------------------------------------------------------------------
# Güvenlik: bu sunucu kullanıcının Ollama/ComfyUI'sine istek ileten bir yerel
# proxy'dir. Eskiden CORS "*" açıktı — kullanıcının ziyaret ettiği HERHANGİ bir
# web sitesi arka planda bu API'yi çağırıp ComfyUI kuyruğuna iş ekleyebilir,
# yerel ağdaki adreslere istek attırabilir ve yanıtları okuyabilirdi. Arayüz
# aynı kökenden sunulduğu için CORS'a ihtiyaç yoktur; gerekirse config.json ->
# server.cors_origins ile açıkça izin verilir. Host başlığı kontrolü de DNS
# rebinding saldırılarını engeller.
# ---------------------------------------------------------------------------
_SERVER_CFG = load_config()["server"]
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}

if _SERVER_CFG.get("cors_origins"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_SERVER_CFG["cors_origins"]),
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


def _hostname(host_header: str) -> str:
    host = (host_header or "").strip().lower()
    if host.startswith("["):  # [::1]:8765
        return host[1:].split("]", 1)[0]
    if host.count(":") == 1:
        return host.split(":", 1)[0]
    return host


_ALLOWED_HOSTS = {h.lower() for h in _SERVER_CFG.get("allowed_hosts") or []}
_ENFORCE_HOST = (
    str(_SERVER_CFG.get("host", "127.0.0.1")).lower() in _LOOPBACK
    or str(_SERVER_CFG.get("host", "")).startswith("127.")
) and "*" not in _ALLOWED_HOSTS


class _HostGuard:
    """Saf ASGI ara katmanı (BaseHTTPMiddleware yerine): istemci bağlantı
    kopmasının uç noktaya iletilmesini — dolayısıyla iptali — bozmaz."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and _ENFORCE_HOST:
            host = dict(scope.get("headers") or []).get(b"host", b"").decode("latin-1")
            if _hostname(host) not in _ALLOWED_HOSTS:
                resp = JSONResponse(
                    status_code=400,
                    content={"detail": {"code": "bad_host", "message": "Geçersiz Host başlığı."}},
                )
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)


app.add_middleware(_HostGuard)

# ---------------------------------------------------------------------------
# Oturumlar SQLite'ta kalıcı saklanır (backend/sessions.py). Burada yalnızca
# LLM'e gönderilen geçmiş uzunluğu ve girdi sınırları tanımlıdır.
# ---------------------------------------------------------------------------
MAX_HISTORY = 24  # sisteme gönderilen geçmiş mesaj sınırı (küçük modellerde bağlamı korur)
MAX_MESSAGE_CHARS = 8000
# Tarayıcı görseli ~1024px JPEG'e küçültür (~200-500 KB); bu sınır yalnızca
# kötüye kullanımı / yanlışlıkla dev dosya gönderimini engeller.
MAX_IMAGE_B64_CHARS = 16 * 1024 * 1024
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,", re.I)
# Arayüzde yeniden göstermek için oturumla birlikte saklanacak en büyük görsel.
MAX_STORED_IMAGE_CHARS = 3 * 1024 * 1024

# İptal edilebilir, sürmekte olan LLM istekleri: request_id -> asyncio.Task
_INFLIGHT: dict = {}


# ---------------------------------------------------------------------------
# Şemalar
# ---------------------------------------------------------------------------
class LLMOverride(BaseModel):
    model: str | None = None
    base_url: str | None = None
    mode: str | None = None
    vision_model: str | None = None


class ChatIn(BaseModel):
    session_id: str | None = None
    message: str = ""
    format_id: str
    family_id: str | None = None
    image: str | None = None  # base64 (düz ya da data URL) — görselden prompt tahmini
    llm: LLMOverride | None = None
    # İstemcinin ürettiği kimlik; /api/chat/cancel ile bu isteği iptal etmeye yarar.
    request_id: str | None = None


class SessionIn(BaseModel):
    session_id: str


class CancelIn(BaseModel):
    request_id: str


class ComfyListIn(BaseModel):
    url: str


class ComfyLoraIn(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    strength_model: float = Field(0.8, ge=-10, le=10)
    strength_clip: float | None = Field(None, ge=-10, le=10)


class ComfySendIn(BaseModel):
    url: str
    checkpoint: str
    positive: str
    negative: str | None = None
    width: int
    height: int
    steps: int
    cfg: float
    sampler: str
    scheduler: str
    seed: int | None = None
    lora: ComfyLoraIn | None = None


def _bad_request(code: str, message: str, status: int = 400, hint: str | None = None):
    detail = {"code": code, "message": message}
    if hint:
        detail["hint"] = hint
    return HTTPException(status, detail=detail)


def _decode_image(raw: str) -> tuple[str, str]:
    """Düz base64 veya data URL alır -> (base64, mime). Geçersizse 400/413."""
    if len(raw) > MAX_IMAGE_B64_CHARS:
        raise _bad_request("image_too_large", "Görsel çok büyük.", 413,
                           "Daha küçük bir görsel deneyin (arayüz görseli otomatik küçültür).")
    mime = "image/jpeg"
    m = _DATA_URL_RE.match(raw)
    if m:
        mime = m.group(1).lower()
        b64 = raw[m.end():]
    elif raw.startswith("data:"):
        raise _bad_request("bad_image", "Desteklenmeyen görsel verisi (base64 data URL bekleniyor).")
    else:
        b64 = raw
    b64 = "".join(b64.split())
    try:
        base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError):
        raise _bad_request("bad_image", "Görsel verisi çözülemedi (geçersiz base64).")
    if not b64:
        raise _bad_request("bad_image", "Görsel verisi boş.")
    return b64, mime


async def _watch_disconnect(request: Request, task: asyncio.Task) -> None:
    """İstemci bağlantıyı kapatırsa (tarayıcıda iptal, sekme kapandı) LLM
    görevini iptal eder. httpx bağlantısı kapanınca Ollama da üretimi durdurur —
    GPU boşuna dakikalarca çalışmaz."""
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                return
            await asyncio.sleep(0.5)
    except Exception:  # izleyici hiçbir koşulda isteği bozmamalı
        pass


async def _run_cancellable(request: Request, request_id: str | None, coro):
    task = asyncio.ensure_future(coro)
    if request_id:
        _INFLIGHT[request_id] = task
    watcher = asyncio.create_task(_watch_disconnect(request, task))
    try:
        await asyncio.wait({task})
    finally:
        watcher.cancel()
        if request_id and _INFLIGHT.get(request_id) is task:
            _INFLIGHT.pop(request_id, None)
        if not task.done():  # sunucu kapanıyor / dış görev iptal edildi
            task.cancel()
    if task.cancelled():
        raise HTTPException(499, detail={"code": "cancelled", "message": "İstek iptal edildi."})
    return task.result()


def _llm_http_error(exc: llm_client.LLMError) -> HTTPException:
    return HTTPException(
        status_code=502,
        detail={"code": exc.code, "message": exc.message, "hint": exc.hint},
    )


# ---------------------------------------------------------------------------
# API uçları
# ---------------------------------------------------------------------------
@app.get("/api/config")
async def get_config():
    cfg = load_config()
    formats = presets.load_formats()
    families, default_family = presets.load_families()
    if default_family not in families:
        default_family = next(iter(families), None)
    return {
        "formats": list(formats.values()),
        "families": [
            {k: v for k, v in fam.items() if k != "llm_guidance"}
            for fam in families.values()
        ],
        "styles": presets.load_styles(),
        "defaults": {
            "format_id": presets.default_format_id(formats),
            "family_id": default_family,
        },
        "llm": {
            "mode": cfg["llm"]["mode"],
            "base_url": cfg["llm"]["base_url"],
            "model": cfg["llm"]["model"],
        },
    }


@app.post("/api/chat")
async def chat(inp: ChatIn, request: Request):
    message = (inp.message or "").strip()
    if not message and not inp.image:
        raise _bad_request("empty", "Mesaj boş olamaz.")
    if len(message) > MAX_MESSAGE_CHARS:
        raise _bad_request("too_long", f"Mesaj çok uzun (en fazla {MAX_MESSAGE_CHARS} karakter).")
    image = _decode_image(inp.image) if inp.image else None
    request_id = inp.request_id if inp.request_id and _SESSION_ID_RE.match(inp.request_id) else None

    cfg = load_config()
    formats = presets.load_formats()
    families, default_family = presets.load_families()

    fmt = formats.get(inp.format_id)
    if fmt is None:
        raise _bad_request("bad_format", "Bilinmeyen format preset'i.")
    family_selected = bool(inp.family_id)
    fam = families.get(inp.family_id or default_family)
    if fam is None:
        raise _bad_request("bad_family", "Bilinmeyen model ailesi.")

    overrides = inp.llm.model_dump(exclude_none=True) if inp.llm else None
    store = get_store()
    # Geçersiz/aşırı uzun oturum kimliği gelirse yeni oturum aç.
    sid = inp.session_id if inp.session_id and _SESSION_ID_RE.match(inp.session_id) else uuid.uuid4().hex
    system_prompt = prompting.build_system_prompt(fmt, fam, family_selected)

    async def pipeline():
        llm_message = message
        # Görsel eklendiyse: önce vision modeliyle İngilizce tarife çevir (2 aşamalı
        # akış), tarifi kullanıcı mesajına göm — sonrası normal metin boru hattı.
        if image:
            b64, mime = image
            desc = await llm_client.describe_image(
                cfg["llm"], b64, prompting.VISION_INSTRUCTION, overrides, mime=mime
            )
            base_text = message or "Bu görseli yeniden oluşturacak bir prompt üret."
            llm_message = f"{base_text}\n\n[Eklenen görselin otomatik analizi]: {desc}"
        messages = (
            [{"role": "system", "content": system_prompt}]
            + store.history(sid, MAX_HISTORY)
            + [{"role": "user", "content": llm_message}]
        )
        raw = await llm_client.chat(cfg["llm"], messages, overrides)
        return llm_message, raw

    try:
        llm_message, raw = await _run_cancellable(request, request_id, pipeline())
    except llm_client.LLMError as exc:
        raise _llm_http_error(exc)

    parsed = prompting.parse_llm_output(raw)
    if parsed["action"] == "generate":
        package = prompting.build_package(fmt, fam, parsed)
        result = {"session_id": sid, "type": "package", "package": package}
        ui_assistant = {"role": "assistant", "kind": "package", "pkg": package}
    else:
        result = {"session_id": sid, "type": "chat", "message": parsed["message"]}
        ui_assistant = {"role": "assistant", "kind": "chat", "text": parsed["message"]}

    # Oturum yalnızca başarılı bir turdan sonra (atomik olarak) yazılır: iptal
    # edilen / hata alan istekler geçmişte iz bırakmaz.
    ui_user = {"role": "user", "kind": "chat", "text": message}
    if image and len(inp.image) <= MAX_STORED_IMAGE_CHARS:
        b64, mime = image
        ui_user["image"] = f"data:{mime};base64,{b64}"
    store.append_turn(
        sid,
        llm_message,
        # <think> blokları geçmişe yazılmaz (bağlam penceresini boşuna doldurur).
        prompting.strip_thinking(raw) or "{}",
        ui_user,
        ui_assistant,
        title=message or "Görselden prompt",
        format_id=fmt["id"],
        family_id=fam["id"],
    )
    return result


@app.post("/api/chat/cancel")
async def chat_cancel(inp: CancelIn):
    task = _INFLIGHT.get(inp.request_id)
    if task is None or task.done():
        return {"ok": True, "cancelled": False}
    # TestClient gibi ortamlarda istek başka bir olay döngüsünde çalışabilir.
    task.get_loop().call_soon_threadsafe(task.cancel)
    return {"ok": True, "cancelled": True}


@app.get("/api/sessions")
async def list_sessions(limit: int = 100):
    return {"sessions": get_store().list_sessions(max(1, min(limit, 500)))}


@app.get("/api/sessions/{sid}")
async def get_session(sid: str):
    sess = get_store().get(sid) if _SESSION_ID_RE.match(sid) else None
    if sess is None:
        raise _bad_request("no_session", "Oturum bulunamadı.", 404)
    return sess


@app.delete("/api/sessions/{sid}")
async def delete_session(sid: str):
    deleted = get_store().delete(sid) if _SESSION_ID_RE.match(sid) else False
    return {"ok": True, "deleted": deleted}


@app.post("/api/session/reset")
async def reset_session(inp: SessionIn):
    """Geriye dönük uyumluluk: oturumu siler (DELETE /api/sessions/{id} ile aynı)."""
    get_store().delete(inp.session_id)
    return {"ok": True}


@app.get("/api/llm/status")
async def llm_status(
    model: str | None = None,
    base_url: str | None = None,
    vision_model: str | None = None,
):
    cfg = load_config()
    overrides = {"model": model, "base_url": base_url, "vision_model": vision_model}
    return await llm_client.status(cfg["llm"], {k: v for k, v in overrides.items() if v})


@app.post("/api/llm/unload")
async def llm_unload(inp: LLMOverride | None = None):
    cfg = load_config()
    overrides = inp.model_dump(exclude_none=True) if inp else None
    return await llm_client.unload(cfg["llm"], overrides)


@app.post("/api/comfyui/checkpoints")
async def comfy_checkpoints(inp: ComfyListIn):
    try:
        return {"checkpoints": await comfyui.list_checkpoints(inp.url)}
    except comfyui.ComfyError as exc:
        raise HTTPException(502, detail={"code": "comfy", "message": exc.message, "hint": exc.hint})


@app.post("/api/comfyui/loras")
async def comfy_loras(inp: ComfyListIn):
    try:
        return {"loras": await comfyui.list_loras(inp.url)}
    except comfyui.ComfyError as exc:
        raise HTTPException(502, detail={"code": "comfy", "message": exc.message, "hint": exc.hint})


@app.post("/api/comfyui/send")
async def comfy_send(inp: ComfySendIn):
    try:
        return await comfyui.send(inp.url, inp.model_dump())
    except comfyui.ComfyError as exc:
        raise HTTPException(502, detail={"code": "comfy", "message": exc.message, "hint": exc.hint})


# ---------------------------------------------------------------------------
# Frontend (önceden derlenmiş dist/ statik olarak sunulur)
# ---------------------------------------------------------------------------
DIST = ROOT / "frontend" / "dist"
if DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="static")
else:

    @app.get("/", response_class=HTMLResponse)
    async def no_frontend():
        return (
            "<h3>Frontend build bulunamadı</h3>"
            "<p><code>frontend/dist</code> klasörü yok. Şunu çalıştırın: "
            "<code>cd frontend && npm install && npm run build</code>, "
            "sonra sunucuyu yeniden başlatın.</p>"
        )


if __name__ == "__main__":
    import uvicorn

    server_cfg = load_config()["server"]
    shown = "127.0.0.1" if server_cfg["host"] in ("0.0.0.0", "::") else server_cfg["host"]
    print(f"\n  ComfyUI Prompt Asistanı -> http://{shown}:{server_cfg['port']}\n")
    uvicorn.run(app, host=server_cfg["host"], port=int(server_cfg["port"]), log_level="info")
