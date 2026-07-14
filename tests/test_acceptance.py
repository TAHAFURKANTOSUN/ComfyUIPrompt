"""Bölüm 10 kabul kriterleri — uçtan uca doğrulama.

Sahte Ollama (tests/mock_ollama.py) 11434 portunda gerçek HTTP sunucusu olarak
çalıştırılır; backend TestClient ile gerçek istek/yanıt döngüsünden geçirilir.
Yalnızca modelin kendisi kurgudur — istemci, ayrıştırıcı, guard'lar, şablon ve
API katmanının tamamı gerçektir.

Çalıştırma (proje kökünden):  python3 tests/test_acceptance.py
"""
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import prompting  # noqa: E402
from backend.main import app  # noqa: E402

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗ HATA'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))


def start_mock():
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "tests.mock_ollama:app",
         "--host", "127.0.0.1", "--port", "11434", "--log-level", "error"],
        cwd=str(ROOT),
    )
    for _ in range(60):
        try:
            httpx.get("http://127.0.0.1:11434/api/tags", timeout=1, trust_env=False)
            return proc
        except Exception:
            time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("Sahte Ollama başlatılamadı")


def chat(client, message, format_id, family_id, session_id=None):
    r = client.post("/api/chat", json={
        "session_id": session_id, "message": message,
        "format_id": format_id, "family_id": family_id,
    })
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    return r.json()


def main():
    mock = start_mock()
    client = TestClient(app)
    try:
        run_all(client)
    finally:
        mock.terminate()

    print(f"\nSONUÇ: {len(PASS)} başarılı, {len(FAIL)} başarısız")
    if FAIL:
        print("Başarısız olanlar:", ", ".join(FAIL))
        sys.exit(1)


def run_all(client):
    req = "sisli bir orman, gizemli atmosfer"

    # ---- Kriter 1: Aynı istek, farklı model ailesi -> belirgin farklı stil ----
    print("\n[1] Model ailesi stil ayrımı (aynı istek, 4 aile)")
    out = {fam: chat(client, req, "desktop_fhd", fam) for fam in ("sd15", "sdxl", "pony", "flux")}
    for fam, r in out.items():
        check(f"{fam}: paket üretildi", r["type"] == "package", str(r)[:200])
    pos = {fam: r["package"]["positive"] for fam, r in out.items()}
    check("4 ailenin positive prompt'u birbirinden farklı", len(set(pos.values())) == 4)
    check("pony: score_9 kalite etiketiyle başlıyor", pos["pony"].startswith("score_9"))
    check("sd15: virgül-etiket yoğun (masterpiece ile başlıyor)", pos["sd15"].startswith("masterpiece"))
    check("flux: etiket yığını değil, akıcı cümle (nokta içeren ≥2 cümle)", pos["flux"].count(".") >= 2 and "score_" not in pos["flux"])
    check("sdxl: <think>+```json sarmalayıcıya rağmen doğru ayrıştırıldı", pos["sdxl"].startswith("a misty ancient forest"))

    # Sistem promptuna aile rehberinin gerçekten enjekte edildiğini doğrula
    fmts, fams = load_presets()
    sys_flux = prompting.build_system_prompt(fmts["desktop_fhd"], fams["flux"])
    sys_pony = prompting.build_system_prompt(fmts["desktop_fhd"], fams["pony"])
    check("flux sistem promptu doğal dil talimatı içeriyor", "DOĞAL DİL" in sys_flux and "null döndür" in sys_flux)
    check("pony sistem promptu booru talimatı içeriyor", "BOORU" in sys_pony.upper() and "score_9" in sys_pony)

    # ---- Kriter 2: Preset değişince üretim çözünürlüğü otomatik değişmeli ----
    print("\n[2] Preset -> çözünürlük eşlemesi")
    r_desk = out["sdxl"]["package"]["settings"]
    r_phone = chat(client, req, "phone", "sdxl")["package"]["settings"]
    r_sd15p = chat(client, req, "phone", "sd15")["package"]["settings"]
    r_avatar = chat(client, req, "avatar", "sdxl")["package"]["settings"]
    check("masaüstü SDXL üretim 1344x768", r_desk["gen"] == [1344, 768], str(r_desk["gen"]))
    check("telefon SDXL üretim 768x1344", r_phone["gen"] == [768, 1344], str(r_phone["gen"]))
    check("telefon hedef 1080x1920", r_phone["target"] == [1080, 1920])
    check("telefon SD1.5 tabanı 432x768 (aile bazlı taban)", r_sd15p["gen"] == [432, 768], str(r_sd15p["gen"]))
    check("avatar: 1024 üret -> 512 downscale etiketi", r_avatar["gen"] == [1024, 1024] and r_avatar["final_label"] == "downscale sonrası")

    # ---- Kriter 3: Flux'ta asla negative prompt üretilmemeli ----
    print("\n[3] Flux negative guard'ı")
    flux_pkg = out["flux"]["package"]
    check("sahte model negative gönderdi ama pakette negative yok", flux_pkg["negative"] is None)
    check("şablonda NEGATIVE PROMPT bölümü yok", "NEGATIVE PROMPT" not in flux_pkg["template_text"])
    check("flux CFG 1.0 + FluxGuidance notu", "FluxGuidance" in flux_pkg["settings"]["cfg"])

    # ---- Kriter 4: Çıktı şablona birebir uymalı ----
    print("\n[4] Bölüm 6 şablonuna birebir uyum")
    parsed = {
        "positive": "mikuv2, cheerful girl singing on neon stage, dynamic pose, confetti",
        "negative": "blurry, lowres",
        "lora": {"name": "miku_v2.safetensors", "trigger": "mikuv2", "weight": 0.8},
        "note": None,
    }
    pkg = prompting.build_package(fmts["phone"], fams["sdxl"], parsed)
    expected = (
        "POSITIVE PROMPT:\n"
        "mikuv2, cheerful girl singing on neon stage, dynamic pose, confetti\n"
        "\n"
        "NEGATIVE PROMPT:\n"
        "blurry, lowres\n"
        "\n"
        "ÖNERİLEN AYARLAR:\n"
        "- Çözünürlük (üretim): 768x1344\n"
        "- Nihai hedef (upscale sonrası): 1080x1920\n"
        "- Sampler: dpmpp_2m (karras)\n"
        "- Steps: 25-30\n"
        "- CFG Scale: 5-7\n"
        "- Model ailesi: SDXL\n"
        "- LoRA (varsa): miku_v2.safetensors + tetikleyici kelime: mikuv2 + önerilen ağırlık: 0.8"
    )
    check("şablon karakteri karaktere eşleşiyor", pkg["template_text"] == expected,
          repr(pkg["template_text"][:120]))
    ep = chat(client, req, "desktop_fhd", "sdxl")["package"]["template_text"]
    for parca in ("POSITIVE PROMPT:", "ÖNERİLEN AYARLAR:", "- Çözünürlük (üretim):",
                  "- Nihai hedef (", "- Sampler:", "- Steps:", "- CFG Scale:", "- Model ailesi:"):
        check(f"canlı yanıt şablon satırı içeriyor: {parca}", parca in ep)

    # ---- Kriter 5: Karakter LoRA / tarif ayrımı ----
    print("\n[5] Karakter akışı (telefon duvar kağıdı + Hatsune Miku)")
    # 5a: Pony — LoRA sorusu -> 'yok' -> booru etiketi
    r1 = chat(client, "Hatsune Miku telefon duvar kağıdı istiyorum", "phone", "pony")
    check("önce LoRA soruldu (chat)", r1["type"] == "chat" and "lora" in r1["message"].lower(), str(r1)[:150])
    r2 = chat(client, "yok", "phone", "pony", session_id=r1["session_id"])
    check("LoRA yok -> booru: karakter+seri etiketi", r2["type"] == "package"
          and "hatsune_miku" in r2["package"]["positive"] and "vocaloid" in r2["package"]["positive"])
    # 5b: SDXL — LoRA sorusu -> 'yok' -> tarif tabanlı (isim geçmez)
    r3 = chat(client, "Hatsune Miku telefon duvar kağıdı", "phone", "sdxl")
    r4 = chat(client, "yok", "phone", "sdxl", session_id=r3["session_id"])
    check("SDXL: isimsiz, tarif tabanlı prompt", r4["type"] == "package"
          and "miku" not in r4["package"]["positive"].lower()
          and "twin-tails" in r4["package"]["positive"])
    check("SDXL: kullanıcıya LoRA önerisi notu", bool(r4["package"]["note"]))
    # 5c: LoRA varsa -> trigger + lora alanı
    r5 = chat(client, "Miku duvar kağıdı", "phone", "sdxl")
    r6 = chat(client, "var, trigger: mikuv2", "phone", "sdxl", session_id=r5["session_id"])
    p6 = r6["package"]
    check("LoRA paketi: trigger positive'in başında", p6["positive"].startswith("mikuv2"))
    check("LoRA alanı dolu (ad+trigger+ağırlık)", p6["lora"] == {"name": "miku_v2.safetensors", "trigger": "mikuv2", "weight": 0.8})
    check("şablonda LoRA satırı var", "- LoRA (varsa): miku_v2.safetensors" in p6["template_text"])

    # ---- [6] Görselden prompt tahmini (vision, iki aşamalı akış) ----
    print("\n[6] Görselden prompt tahmini (vision)")
    img_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
        "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )  # 1x1 PNG — sahte vision modeli içeriğe bakmaz, boru hattını test ederiz
    rimg = client.post("/api/chat", json={
        "message": "", "image": img_b64, "format_id": "phone", "family_id": "flux",
    })
    ok_img = rimg.status_code == 200 and rimg.json().get("type") == "package"
    check("boş metin + görsel -> paket üretildi", ok_img, rimg.text[:200])
    if ok_img:
        vp = rimg.json()["package"]
        check("görsel analizi prompt'a dönüştü (sahne eşleşti)", "forest" in vp["positive"].lower())
        check("görsel akışında da Flux negative guard'ı çalışıyor", vp["negative"] is None)
        check("görsel akışında çözünürlük preset'ten (768x1344)", vp["settings"]["gen"] == [768, 1344])
    rimg2 = client.post("/api/chat", json={
        "message": "buna benzer ama daha karanlık olsun",
        "image": "data:image/png;base64," + img_b64,
        "format_id": "desktop_fhd", "family_id": "pony",
    })
    ok2 = rimg2.status_code == 200 and rimg2.json().get("type") == "package"
    check("dataURL öneki ayıklanıyor + görsel pony stiline çevriliyor",
          ok2 and rimg2.json()["package"]["positive"].startswith("score_9"), rimg2.text[:200])
    rv = client.post("/api/chat", json={
        "message": "", "image": img_b64, "format_id": "phone", "family_id": "sdxl",
        "llm": {"vision_model": "olmayan-vl:7b"},
    })
    dv = rv.json().get("detail", {}) if rv.status_code != 200 else {}
    check("vision modeli yüklü değilse 502 + `ollama pull` ipucu",
          rv.status_code == 502 and "ollama pull" in (dv.get("hint") or ""), rv.text[:200])
    st2 = client.get("/api/llm/status").json()
    check("status vision modeli bilgisini raporluyor",
          "vision_model" in st2 and "vision_available" in st2)

    # ---- Ek sağlamlık kontrolleri ----
    print("\n[+] Sağlamlık / hata yolları")
    r = chat(client, "kısa bir şey", "ig_post", "sdxl")
    check("eksik bilgi -> soru moduna geçiyor", r["type"] == "chat" and "?" in r["message"])
    r = chat(client, "hata ver bakalım", "ig_post", "sdxl")
    check("bozuk model çıktısı sohbete düşüyor (çökmüyor)", r["type"] == "chat")
    bad = client.post("/api/chat", json={"message": "x", "format_id": "olmayan", "family_id": "sdxl"})
    check("bilinmeyen preset -> 400", bad.status_code == 400)
    empty = client.post("/api/chat", json={"message": "  ", "format_id": "phone", "family_id": "sdxl"})
    check("boş mesaj -> 400", empty.status_code == 400)
    down = client.post("/api/chat", json={"message": "orman", "format_id": "phone", "family_id": "sdxl",
                                          "llm": {"base_url": "http://127.0.0.1:9"}})
    d = down.json().get("detail", {})
    check("Ollama kapalı -> 502 + Türkçe ipucu", down.status_code == 502 and "hint" in d and d["code"] == "unreachable")
    st = client.get("/api/llm/status").json()
    check("durum ucu model listesi veriyor", st["ok"] and "qwen3:8b" in st["models"])
    cfg = client.get("/api/config").json()
    check("config: 9 format + 4 aile + stiller", len(cfg["formats"]) == 9 and len(cfg["families"]) == 4 and len(cfg["styles"]) > 0)
    check("aile listesinde llm_guidance sızmıyor", all("llm_guidance" not in f for f in cfg["families"]))
    # formats.json bütünlüğü
    ok8 = all(all(v % 8 == 0 for v in f["gen"]) and all(v % 8 == 0 for v in f.get("gen_sd15", f["gen"])) for f in cfg["formats"])
    check("tüm üretim çözünürlükleri 8'in katı", ok8)
    # varsayılan aile (family_id gönderilmezse SDXL)
    rdef = client.post("/api/chat", json={"message": "orman", "format_id": "phone"}).json()
    check("aile seçilmezse varsayılan SDXL", rdef["package"]["settings"]["family_id"] == "sdxl")


def load_presets():
    from backend import presets
    formats = presets.load_formats()
    families, _ = presets.load_families()
    return formats, families


if __name__ == "__main__":
    main()
