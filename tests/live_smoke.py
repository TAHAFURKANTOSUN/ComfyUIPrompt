"""Gerçek Ollama ile canlı duman testi — KENDİ makinenizde çalıştırın.

Sahte model yerine gerçek yerel LLM'le aynı senaryoları koşturur ve çıktıları
gözle kontrol etmeniz için ekrana basar. Kural tabanlı kontroller (Flux'ta
negative olmaması, çözünürlükler, şablon) otomatik doğrulanır; prompt KALİTESİ
model büyüklüğüne bağlıdır (qwen3:8b ve üzeri önerilir).

Kullanım:
  1) Backend'i başlatın:  python -m backend.main
  2) Başka bir terminalde: python tests/live_smoke.py  [--url http://127.0.0.1:8765]
  3) Görselden-prompt (vision) akışını da test etmek için:
     python tests/live_smoke.py --image bir_resim.jpg
"""
import argparse
import base64
import sys

import httpx

SCENARIOS = [
    ("Telefon + SDXL", "phone", "sdxl", ["sisli bir orman, gizemli atmosfer, tepede yalnız bir geyik"]),
    ("Telefon + Flux (negative yasağı)", "phone", "flux", ["sisli bir orman, gizemli atmosfer, tepede yalnız bir geyik"]),
    ("Masaüstü + Pony (anime karakter)", "desktop_fhd", "pony", ["Hatsune Miku duvar kağıdı istiyorum, sahnede konser veriyor", "yok"]),
    ("Telefon + SDXL (anime karakter, tarif modu)", "phone", "sdxl", ["Hatsune Miku duvar kağıdı", "lora yok"]),
    ("Ultrawide + SD1.5", "ultrawide", "sd15", ["gün batımında fütüristik şehir silueti, mor-turuncu gökyüzü"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8765")
    ap.add_argument("--image", help="Bir görsel dosyası verin; görselden-prompt (vision) senaryosu da koşulur")
    args = ap.parse_args()
    base = args.url.rstrip("/")

    st = httpx.get(f"{base}/api/llm/status", timeout=10, trust_env=False).json()
    print(f"LLM durumu: ok={st['ok']} model={st['configured_model']} yüklü={st['model_available']}")
    if not st["ok"]:
        print("Ollama'ya ulaşılamıyor — önce `ollama serve` ve `ollama pull qwen3:8b` çalıştırın.")
        sys.exit(1)

    problems = []
    for title, fmt, fam, turns in SCENARIOS:
        print("\n" + "=" * 70 + f"\n▶ {title}  (format={fmt}, aile={fam})")
        sid = None
        last = None
        for msg in turns:
            print(f"  kullanıcı> {msg}")
            r = httpx.post(f"{base}/api/chat", json={
                "session_id": sid, "message": msg, "format_id": fmt, "family_id": fam,
            }, timeout=600, trust_env=False)
            if r.status_code != 200:
                print(f"  !! HTTP {r.status_code}: {r.text[:300]}")
                problems.append(f"{title}: HTTP {r.status_code}")
                break
            data = r.json()
            sid = data["session_id"]
            last = data
            if data["type"] == "chat":
                print(f"  asistan> {data['message']}")
            else:
                print("  --- ÜRETİLEN PAKET " + "-" * 40)
                print("  " + data["package"]["template_text"].replace("\n", "\n  "))

        if last and last["type"] == "package":
            pkg = last["package"]
            s = pkg["settings"]
            if fam == "flux" and pkg["negative"] is not None:
                problems.append(f"{title}: Flux'ta negative üretildi!")
            if fam == "flux" and "NEGATIVE" in pkg["template_text"]:
                problems.append(f"{title}: şablonda NEGATIVE bölümü var!")
            if s["family_id"] != fam:
                problems.append(f"{title}: aile uyuşmazlığı")
            print(f"  [kontrol] çözünürlük={s['gen']} hedef={s['target']} negative={'yok' if pkg['negative'] is None else 'var'}")
        elif last and last["type"] == "chat":
            print("  [bilgi] Senaryo soru turunda bitti (model daha fazla bilgi istedi).")

    if args.image:
        print("\n" + "=" * 70 + "\n▶ Görselden prompt (vision)  (format=phone, aile=sdxl)")
        if not st.get("vision_available"):
            print(f"  Uyarı: vision modeli ({st.get('vision_model')}) yüklü görünmüyor — `ollama pull {st.get('vision_model')}`")
        with open(args.image, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        r = httpx.post(f"{base}/api/chat", json={
            "message": "", "image": b64, "format_id": "phone", "family_id": "sdxl",
        }, timeout=600, trust_env=False)
        if r.status_code != 200:
            print(f"  !! HTTP {r.status_code}: {r.text[:300]}")
            problems.append(f"Vision: HTTP {r.status_code}")
        else:
            data = r.json()
            if data["type"] == "package":
                print("  --- ÜRETİLEN PAKET " + "-" * 40)
                print("  " + data["package"]["template_text"].replace("\n", "\n  "))
            else:
                print(f"  asistan> {data['message']}")

    print("\n" + "=" * 70)
    if problems:
        print("SORUNLAR:")
        for p in problems:
            print(" -", p)
        sys.exit(1)
    print("Kural kontrolleri geçti. Prompt kalitesini yukarıdaki çıktılardan gözle değerlendirin.")


if __name__ == "__main__":
    main()
