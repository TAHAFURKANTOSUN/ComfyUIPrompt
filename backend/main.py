"""ComfyUI Prompt Asistanı — FastAPI backend.

Çalıştırma (proje kökünden):
    python -m backend.main
veya:
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
"""
import base64
import binascii
import re
import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import comfyui, llm_client, presets, prompting
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


@app.middleware("http")
async def _host_guard(request: Request, call_next):
    if _ENFORCE_HOST and _hostname(request.headers.get("host", "")) not in _ALLOWED_HOSTS:
        return JSONResponse(
            status_code=400,
            content={"detail": {"code": "bad_host", "message": "Geçersiz Host başlığı."}},
        )
    return await call_next(request)

# ---------------------------------------------------------------------------
# Oturum durumu (in-memory — görev tanımına göre kalıcı saklama gerekmiyor)
# ---------------------------------------------------------------------------
SESSIONS: dict = {}
MAX_SESSIONS = 200
MAX_HISTORY = 24  # sisteme gönderilen geçmiş mesaj sınırı (küçük modellerde bağlamı korur)
MAX_MESSAGE_CHARS = 8000
# Tarayıcı görseli ~1024px JPEG'e küçültür (~200-500 KB); bu sınır yalnızca
# kötüye kullanımı / yanlışlıkla dev dosya gönderimini engeller.
MAX_IMAGE_B64_CHARS = 16 * 1024 * 1024
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_DATA_URL_RE = re.compile(r"^data:(image/[a-zA-Z0-9.+-]+);base64,", re.I)


def _prune_sessions() -> None:
    if len(SESSIONS) <= MAX_SESSIONS:
        return
    for sid in sorted(SESSIONS, key=lambda s: SESSIONS[s]["t"])[: len(SESSIONS) - MAX_SESSIONS]:
        SESSIONS.pop(sid, None)


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


class SessionIn(BaseModel):
    session_id: str


class ComfyListIn(BaseModel):
    url: str


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
async def chat(inp: ChatIn):
    message = (inp.message or "").strip()
    if not message and not inp.image:
        raise _bad_request("empty", "Mesaj boş olamaz.")
    if len(message) > MAX_MESSAGE_CHARS:
        raise _bad_request("too_long", f"Mesaj çok uzun (en fazla {MAX_MESSAGE_CHARS} karakter).")
    image = _decode_image(inp.image) if inp.image else None

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

    # Görsel eklendiyse: önce vision modeliyle İngilizce tarife çevir (2 aşamalı akış),
    # tarifi kullanıcı mesajına göm — sonrası normal metin boru hattıyla aynı.
    if image:
        b64, mime = image
        try:
            desc = await llm_client.describe_image(
                cfg["llm"], b64, prompting.VISION_INSTRUCTION, overrides, mime=mime
            )
        except llm_client.LLMError as exc:
            raise _llm_http_error(exc)
        base_text = message or "Bu görseli yeniden oluşturacak bir prompt üret."
        message = f"{base_text}\n\n[Eklenen görselin otomatik analizi]: {desc}"

    # Geçersiz/aşırı uzun oturum kimliği gelirse yeni oturum aç.
    sid = inp.session_id if inp.session_id and _SESSION_ID_RE.match(inp.session_id) else uuid.uuid4().hex
    sess = SESSIONS.setdefault(sid, {"messages": [], "t": time.time()})
    sess["t"] = time.time()
    _prune_sessions()

    system_prompt = prompting.build_system_prompt(fmt, fam, family_selected)
    messages = (
        [{"role": "system", "content": system_prompt}]
        + sess["messages"][-MAX_HISTORY:]
        + [{"role": "user", "content": message}]
    )

    try:
        raw = await llm_client.chat(cfg["llm"], messages, overrides)
    except llm_client.LLMError as exc:
        raise _llm_http_error(exc)

    parsed = prompting.parse_llm_output(raw)
    sess["messages"].append({"role": "user", "content": message})
    # <think> blokları geçmişe yazılmaz (bağlam penceresini boşuna doldurur).
    sess["messages"].append({"role": "assistant", "content": prompting.strip_thinking(raw) or "{}"})
    sess["messages"] = sess["messages"][-MAX_HISTORY * 2 :]

    if parsed["action"] == "generate":
        package = prompting.build_package(fmt, fam, parsed)
        return {"session_id": sid, "type": "package", "package": package}
    return {"session_id": sid, "type": "chat", "message": parsed["message"]}


@app.post("/api/session/reset")
async def reset_session(inp: SessionIn):
    SESSIONS.pop(inp.session_id, None)
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
