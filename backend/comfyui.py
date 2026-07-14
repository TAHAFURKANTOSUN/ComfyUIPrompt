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


async def list_checkpoints(url: str) -> list:
    url = _norm_url(url)
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(10.0, connect=4.0)) as client:
            resp = await client.get(f"{url}/object_info/CheckpointLoaderSimple")
            resp.raise_for_status()
            data = resp.json()
        return data["CheckpointLoaderSimple"]["input"]["required"]["ckpt_name"][0]
    except httpx.ConnectError:
        raise ComfyError(
            f"ComfyUI'ye ulaşılamıyor ({url}).",
            "ComfyUI'nin açık olduğundan ve adresin doğru olduğundan emin olun.",
        )
    except (KeyError, IndexError, ValueError):
        raise ComfyError("ComfyUI beklenmeyen bir yanıt döndürdü (checkpoint listesi okunamadı).")


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
    ks["seed"] = int(req.get("seed") or random.randint(0, 2**48))
    ks["steps"] = int(req.get("steps") or 28)
    ks["cfg"] = float(req.get("cfg") or 6.0)
    ks["sampler_name"] = req.get("sampler") or "dpmpp_2m"
    ks["scheduler"] = req.get("scheduler") or "karras"

    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(20.0, connect=4.0)) as client:
            resp = await client.post(
                f"{url}/prompt", json={"prompt": wf, "client_id": CLIENT_ID}
            )
    except httpx.ConnectError:
        raise ComfyError(
            f"ComfyUI'ye ulaşılamıyor ({url}).",
            "ComfyUI'nin açık olduğundan emin olun.",
        )
    if resp.status_code >= 400:
        detail = resp.text[:400]
        hint = None
        if "sampler_name" in detail:
            hint = "Seçili sampler bu ComfyUI sürümünde yok olabilir."
        elif "ckpt_name" in detail:
            hint = "Checkpoint adı sunucudakiyle eşleşmiyor; listeden yeniden seçin."
        raise ComfyError(f"ComfyUI isteği reddetti: {detail}", hint)
    data = resp.json()
    return {"ok": True, "prompt_id": data.get("prompt_id"), "seed": ks["seed"]}
