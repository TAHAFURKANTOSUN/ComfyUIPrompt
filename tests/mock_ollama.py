"""Sahte Ollama sunucusu — testler için.

Gerçek Ollama API yüzeyini (/api/chat, /api/tags) taklit eder ve sistem
promptundaki model ailesine göre 'gerçekçi' hazır yanıtlar döndürür. Böylece
uygulamanın TÜM boru hattı (HTTP istemcisi, format kademeli düşüşü, ayrıştırma,
guard'lar, şablon) gerçek ağ üzerinden test edilir; yalnızca modelin kendisi
kurgudur.

Kasıtlı davranışlar:
  - Flux yanıtına BİLEREK negative_prompt konur -> backend guard'ının bunu
    silmesi beklenir (kabul kriteri 3).
  - SDXL orman yanıtı <think> bloğu + ```json çiti içine sarılır -> ayrıştırıcı
    dayanıklılığı test edilir.
  - Karakter isteklerinde önce LoRA sorusu sorulur (kabul kriteri 5).
  - "yavaş" içeren istekler 30 sn bekletilir -> iptal mekanizması test edilir.
"""
import asyncio
import json  # v1.1 — vision (görsel analizi) davranışı dahil

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

# Vision (görsel analizi) çağrılarına dönen hazır tarif — 'forest' içerir ki
# ikinci aşama (metin modeli) FOREST senaryosuna yönlensin.
VISION_DESCRIPTION = (
    "A misty ancient forest at dawn: towering moss-covered pine trees dissolve into "
    "pale silver fog, soft volumetric light rays cut between the trunks, damp ferns "
    "cover the ground. Painterly digital art style, wide cinematic composition, muted "
    "palette of deep greens, teal shadows and warm amber highlights, quiet mysterious mood."
)


def _family(system: str) -> str:
    if "Model ailesi: Flux" in system:
        return "flux"
    if "Model ailesi: Pony" in system:
        return "pony"
    if "Model ailesi: SD 1.5" in system:
        return "sd15"
    return "sdxl"


FOREST = {
    "sdxl": {
        "action": "generate",
        "positive_prompt": "a misty ancient forest at dawn, towering moss-covered pines fading into fog. mysterious ethereal atmosphere, (volumetric god rays:1.2), soft diffused lighting, wide establishing shot, muted teal and amber palette, highly detailed, sharp focus",
        "negative_prompt": "blurry, lowres, bad anatomy, deformed, watermark, text, oversaturated",
        "lora": None,
        "note": None,
    },
    "sd15": {
        "action": "generate",
        "positive_prompt": "masterpiece, best quality, highly detailed, misty forest, dense fog, ancient trees, moss, (volumetric lighting:1.3), god rays, mysterious atmosphere, muted colors, wide shot, depth of field",
        "negative_prompt": "worst quality, low quality, lowres, bad anatomy, bad hands, extra fingers, missing fingers, cropped, jpeg artifacts, signature, watermark, username, text, blurry",
        "lora": None,
        "note": None,
    },
    "pony": {
        "action": "generate",
        "positive_prompt": "score_9, score_8_up, score_7_up, masterpiece, best quality, no humans, forest, mist, fog, ancient trees, moss, sunbeam, dappled sunlight, scenery, wide shot, muted palette, mysterious atmosphere",
        "negative_prompt": "score_6, score_5, score_4, worst quality, low quality, bad anatomy, bad hands, extra digits, watermark, signature, jpeg artifacts",
        "lora": None,
        "note": None,
    },
    "flux": {
        "action": "generate",
        "positive_prompt": "An ancient forest wrapped in slow-moving morning mist, where towering moss-covered pines dissolve into a pale silver haze. Soft diffused light filters between the trunks, casting long gentle rays across damp ferns. The mood is quiet and mysterious, with a muted palette of deep greens, teal shadows and warm amber highlights.",
        "negative_prompt": "blurry, ugly, deformed",  # KASITLI: guard silmeli
        "lora": None,
        "note": None,
    },
}

LORA_QUESTION = {
    "action": "chat",
    "message": "Bu karakter için elinde özel bir LoRA var mı? Varsa tetikleyici kelimesini (trigger word) yaz; yoksa 'yok' demen yeterli.",
}

CHAR_NO_LORA = {
    "pony": {
        "action": "generate",
        "positive_prompt": "score_9, score_8_up, score_7_up, masterpiece, best quality, hatsune_miku, vocaloid, 1girl, aqua_hair, twintails, aqua_eyes, detached_sleeves, necktie, thigh_boots, singing, stage lights, dynamic pose, cowboy shot",
        "negative_prompt": "score_6, score_5, score_4, worst quality, low quality, bad anatomy, bad hands, extra digits, watermark, signature",
        "lora": None,
        "note": "Booru-tabanlı model karakter adını doğrudan etiket olarak tanır; LoRA gerekmedi.",
    },
    "sdxl": {
        "action": "generate",
        "positive_prompt": "a cheerful anime girl with very long turquoise twin-tails, bright teal eyes, futuristic grey sleeveless top with teal necktie, black detached sleeves, thigh-high boots, singing on a neon-lit stage. cel-shaded anime style, dynamic pose, vibrant stage lighting, highly detailed",
        "negative_prompt": "blurry, lowres, bad anatomy, bad hands, deformed, watermark, text",
        "lora": None,
        "note": "SDXL karakter ismini güvenilir tanımadığı için isim yerine görsel tarif kullanıldı; en doğru sonuç için Civitai'de karakter LoRA'sı aramanı öneririm.",
    },
}

CHAR_WITH_LORA = {
    "action": "generate",
    "positive_prompt": "mikuv2, cheerful girl singing on a neon-lit stage, dynamic pose, confetti falling, vibrant lighting, highly detailed",
    "negative_prompt": "blurry, lowres, bad anatomy, watermark",
    "lora": {"name": "miku_v2.safetensors", "trigger": "mikuv2", "weight": 0.8},
    "note": None,
}

VAGUE_QUESTION = {
    "action": "chat",
    "message": "Birkaç kısa soru: 1) Ana özne ne olsun? 2) Işık/ruh hali nasıl (ör. gün batımı, karanlık, neşeli)? 3) Belirli bir sanat stili ister misin?",
}


def decide(messages: list) -> str:
    system = messages[0]["content"] if messages else ""
    fam = _family(system)
    users = [m["content"] for m in messages if m.get("role") == "user"]
    last = (users[-1] if users else "").lower()
    asked_lora = any(
        "lora" in (m.get("content") or "").lower()
        for m in messages
        if m.get("role") == "assistant"
    )

    if "miku" in last and not asked_lora:
        return json.dumps(LORA_QUESTION, ensure_ascii=False)
    if asked_lora and ("trigger" in last or "mikuv2" in last):
        return json.dumps(CHAR_WITH_LORA, ensure_ascii=False)
    if asked_lora and "yok" in last:
        payload = CHAR_NO_LORA.get(fam, CHAR_NO_LORA["sdxl"])
        return json.dumps(payload, ensure_ascii=False)
    if "orman" in last or "forest" in last:
        payload = json.dumps(FOREST[fam], ensure_ascii=False)
        if fam == "sdxl":
            # ayrıştırıcı dayanıklılık testi: düşünce bloğu + kod çiti + fazladan laf
            return f"<think>kullanıcı sisli orman istiyor, sdxl stili...</think>\nİşte prompt:\n```json\n{payload}\n```"
        return payload
    if "hata" in last:
        return "bu gecerli bir json degil {{{"
    return json.dumps(VAGUE_QUESTION, ensure_ascii=False)


@app.get("/api/tags")
async def tags():
    return {"models": [{"name": "qwen3:8b"}, {"name": "qwen3:0.6b"}]}


@app.post("/api/chat")
async def chat(request: Request):
    body = await request.json()
    model = body.get("model", "mock")
    messages = body.get("messages", [])

    # Gerçek Ollama davranışı: yüklü olmayan model -> 404 "not found"
    if "olmayan" in model:
        return JSONResponse(status_code=404, content={"error": f"model '{model}' not found"})

    # Görsel içeren istek -> vision modeli gibi davran: düz metin tarif döndür
    if any(m.get("images") for m in messages):
        return {
            "model": model,
            "message": {"role": "assistant", "content": VISION_DESCRIPTION},
            "done": True,
        }

    # İptal testi: "yavaş" içeren istek çok uzun sürer (büyük model taklidi).
    users = [m.get("content", "") for m in messages if m.get("role") == "user"]
    if users and "yavaş" in users[-1].lower():
        # Gerçek Ollama gibi: istemci bağlantıyı kapatırsa üretimi bırak.
        for _ in range(150):
            if await request.is_disconnected():
                print("[mock-ollama] istemci bağlantıyı kesti, üretim durduruldu", flush=True)
                return JSONResponse(status_code=499, content={"error": "client disconnected"})
            await asyncio.sleep(0.2)

    content = decide(messages)
    return {
        "model": model,
        "message": {"role": "assistant", "content": content},
        "done": True,
    }
