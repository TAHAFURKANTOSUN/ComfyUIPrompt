"""ComfyUI Prompt Asistanı — FastAPI backend.

Çalıştırma (proje kökünden):
    python -m backend.main
veya:
    python -m uvicorn backend.main:app --host 127.0.0.1 --port 8765
"""
import time
import uuid

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import comfyui, llm_client, presets, prompting
from .config import ROOT, load_config

app = FastAPI(title="ComfyUI Prompt Asistanı")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# ---------------------------------------------------------------------------
# Oturum durumu (in-memory — görev tanımına göre kalıcı saklama gerekmiyor)
# ---------------------------------------------------------------------------
SESSIONS: dict = {}
MAX_SESSIONS = 200
MAX_HISTORY = 24  # sisteme gönderilen geçmiş mesaj sınırı (küçük modellerde bağlamı korur)


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


# ---------------------------------------------------------------------------
# API uçları
# ---------------------------------------------------------------------------
@app.get("/api/config")
async def get_config():
    cfg = load_config()
    formats = presets.load_formats()
    families, default_family = presets.load_families()
    return {
        "formats": list(formats.values()),
        "families": [
            {k: v for k, v in fam.items() if k != "llm_guidance"}
            for fam in families.values()
        ],
        "styles": presets.load_styles(),
        "defaults": {"format_id": "desktop_fhd", "family_id": default_family},
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
        raise HTTPException(400, detail={"code": "empty", "message": "Mesaj boş olamaz."})

    cfg = load_config()
    formats = presets.load_formats()
    families, default_family = presets.load_families()

    fmt = formats.get(inp.format_id)
    if fmt is None:
        raise HTTPException(400, detail={"code": "bad_format", "message": "Bilinmeyen format preset'i."})
    family_selected = bool(inp.family_id)
    fam = families.get(inp.family_id or default_family)
    if fam is None:
        raise HTTPException(400, detail={"code": "bad_family", "message": "Bilinmeyen model ailesi."})

    sid = inp.session_id or uuid.uuid4().hex
    sess = SESSIONS.setdefault(sid, {"messages": [], "t": time.time()})
    sess["t"] = time.time()
    _prune_sessions()

    system_prompt = prompting.build_system_prompt(fmt, fam, family_selected)
    messages = (
        [{"role": "system", "content": system_prompt}]
        + sess["messages"][-MAX_HISTORY:]
        + [{"role": "user", "content": message}]
    )

    overrides = inp.llm.model_dump(exclude_none=True) if inp.llm else None

    # Görsel eklendiyse: önce vision modeliyle İngilizce tarife çevir (2 aşamalı akış),
    # tarifi kullanıcı mesajına göm — sonrası normal metin boru hattıyla aynı.
    if inp.image:
        b64 = inp.image.split(",", 1)[1] if inp.image.startswith("data:") else inp.image
        try:
            desc = await llm_client.describe_image(
                cfg["llm"], b64, prompting.VISION_INSTRUCTION, overrides
            )
        except llm_client.LLMError as exc:
            raise HTTPException(
                status_code=502,
                detail={"code": exc.code, "message": exc.message, "hint": exc.hint},
            )
        base_text = message or "Bu görseli yeniden oluşturacak bir prompt üret."
        message = f"{base_text}\n\n[Eklenen görselin otomatik analizi]: {desc}"
        # mesajlar listesindeki son kullanıcı mesajını da güncelle
        messages = messages[:-1] + [{"role": "user", "content": message}]

    try:
        raw = await llm_client.chat(cfg["llm"], messages, overrides)
    except llm_client.LLMError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": exc.code, "message": exc.message, "hint": exc.hint},
        )

    parsed = prompting.parse_llm_output(raw)
    sess["messages"].append({"role": "user", "content": message})
    sess["messages"].append({"role": "assistant", "content": raw.strip() or "{}"})
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
    print(f"\n  ComfyUI Prompt Asistanı -> http://{server_cfg['host']}:{server_cfg['port']}\n")
    uvicorn.run(app, host=server_cfg["host"], port=int(server_cfg["port"]), log_level="info")
