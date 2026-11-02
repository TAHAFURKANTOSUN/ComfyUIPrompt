"""Bölüm 10 kabul kriterleri — uçtan uca doğrulama.

Sahte Ollama (tests/mock_ollama.py) boş bir yerel portta gerçek HTTP sunucusu
olarak çalıştırılır (makinede gerçek Ollama 11434'te açık olsa bile çakışmaz);
backend TestClient ile gerçek istek/yanıt döngüsünden geçirilir.
Yalnızca modelin kendisi kurgudur — istemci, ayrıştırıcı, guard'lar, şablon ve
API katmanının tamamı gerçektir.

Çalıştırma (proje kökünden):  python3 tests/test_acceptance.py
"""
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


MOCK_PORT = _free_port()
MOCK_URL = f"http://127.0.0.1:{MOCK_PORT}"
COMFY_PORT = _free_port()
COMFY_URL = f"http://127.0.0.1:{COMFY_PORT}"
# Backend config'i her istekte okur; ortam değişkeni config.json'u ezer.
os.environ["OLLAMA_BASE_URL"] = MOCK_URL
# Oturumlar geçici bir SQLite dosyasına yazılır (kullanıcının geçmişine dokunulmaz).
TMP_DIR = tempfile.TemporaryDirectory(prefix="cpa-test-")
DB_PATH = os.path.join(TMP_DIR.name, "sessions.db")
os.environ["SESSIONS_DB"] = DB_PATH

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import llm_client, prompting  # noqa: E402
from backend.main import app  # noqa: E402
from backend.sessions import SessionStore, get_store  # noqa: E402

PASS, FAIL = [], []


def check(name: str, cond: bool, detail: str = ""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✓' if cond else '✗ HATA'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))


def start_mock(module="tests.mock_ollama:app", port=None, probe="/api/tags"):
    port = port or MOCK_PORT
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", module,
         "--host", "127.0.0.1", "--port", str(port), "--log-level", "error"],
        cwd=str(ROOT),
    )
    for _ in range(60):
        if proc.poll() is not None:
            raise RuntimeError(f"Sahte sunucu ({module}) beklenmedik şekilde kapandı")
        try:
            httpx.get(f"http://127.0.0.1:{port}{probe}", timeout=1, trust_env=False)
            return proc
        except Exception:
            time.sleep(0.25)
    proc.terminate()
    raise RuntimeError(f"Sahte sunucu ({module}) başlatılamadı")


def chat(client, message, format_id, family_id, session_id=None):
    r = client.post("/api/chat", json={
        "session_id": session_id, "message": message,
        "format_id": format_id, "family_id": family_id,
    })
    assert r.status_code == 200, f"HTTP {r.status_code}: {r.text[:300]}"
    return r.json()


def main():
    mock = start_mock()
    comfy = start_mock("tests.mock_comfyui:app", COMFY_PORT, "/object_info/LoraLoader")
    # Host başlığı koruması loopback dışını reddeder; TestClient'ın varsayılan
    # "testserver" host'u yerine gerçek kullanımdaki adresi taklit et.
    client = TestClient(app, base_url="http://127.0.0.1:8765")
    try:
        run_all(client)
        run_review_checks(client)
        run_feature_checks(client)
    finally:
        for proc in (mock, comfy):
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        get_store().close()
        TMP_DIR.cleanup()

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


def run_review_checks(client):
    """Kod incelemesinde bulunan hataların regresyon kontrolleri."""
    print("\n[R] İnceleme düzeltmeleri (güvenlik / sağlamlık)")

    # Güvenlik: başka bir site API'yi tarayıcı üzerinden kullanamamalı.
    pre = client.options("/api/chat", headers={
        "Origin": "https://kotu-site.example", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type"})
    check("CORS: yabancı kökene izin verilmiyor",
          pre.headers.get("access-control-allow-origin") is None, str(dict(pre.headers))[:200])
    reb = client.get("/api/config", headers={"Host": "kotu-site.example"})
    check("DNS rebinding: yabancı Host başlığı reddediliyor", reb.status_code == 400)
    ok_hosts = all(client.get("/api/config", headers={"Host": h}).status_code == 200
                   for h in ("127.0.0.1:8765", "localhost:5173", "[::1]:8765"))
    check("loopback Host başlıkları kabul ediliyor", ok_hosts)

    # Model eşleşmesi: qwen3:8b yüklü diye qwen3:14b 'yüklü' sayılmamalı.
    st = client.get("/api/llm/status", params={"model": "qwen3:14b"}).json()
    check("status: farklı boyut etiketi 'yüklü' sayılmıyor", st["ok"] and not st["model_available"])
    st = client.get("/api/llm/status", params={"model": "qwen3:8b"}).json()
    check("status: tam eşleşen model 'yüklü'", st["model_available"])
    check("model eşleşmesi: etiketsiz ad ':latest' sayılıyor",
          llm_client._model_matches("llava", ["llava:latest"])
          and not llm_client._model_matches("llava", ["llava:13b"]))

    # Geçmişe <think> blokları yazılmamalı.
    r = chat(client, "sisli bir orman", "phone", "sdxl")
    hist = get_store().history(r["session_id"], 100)
    check("sohbet geçmişinde <think> bloğu saklanmıyor",
          all("<think>" not in m["content"] for m in hist))

    # Girdi doğrulama.
    big = client.post("/api/chat", json={"message": "x" * 9000, "format_id": "phone"})
    check("aşırı uzun mesaj -> 400", big.status_code == 400 and big.json()["detail"]["code"] == "too_long")
    bad_img = client.post("/api/chat", json={"message": "", "image": "bu-base64-degil!!", "format_id": "phone"})
    check("geçersiz base64 görsel -> 400 bad_image",
          bad_img.status_code == 400 and bad_img.json()["detail"]["code"] == "bad_image")
    weird_sid = client.post("/api/chat", json={"message": "orman", "format_id": "phone",
                                               "session_id": "../" + "a" * 500})
    check("geçersiz session_id -> yeni oturum açılıyor",
          weird_sid.status_code == 200 and len(weird_sid.json()["session_id"]) == 32)

    # Görsel başarısız olursa boş oturum oluşmamalı.
    before = get_store().count()
    client.post("/api/chat", json={"message": "", "image": "iVBORw0KGgo=", "format_id": "phone",
                                   "llm": {"vision_model": "olmayan-vl"}})
    check("vision hatasında boş oturum oluşturulmuyor", get_store().count() == before)

    # Varsayılan format formats.json'dan geliyor.
    cfg = client.get("/api/config").json()
    check("varsayılan format formats.json 'default' alanından",
          cfg["defaults"]["format_id"] == "desktop_fhd")

    # Şablon: hedef == üretim ise 'upscale' yazmamalı (SD1.5 + avatar 512->512).
    fmts, fams = load_presets()
    pkg = prompting.build_package(fmts["avatar"], fams["sd15"], {"positive": "x"})
    check("SD1.5 avatar: 512->512 'ölçekleme gerekmez' etiketi",
          pkg["settings"]["final_label"] == "ölçekleme gerekmez")
    check("sistem promptunda yinelenen madde numarası yok",
          prompting.SYSTEM_PROMPT_BASE.count("\n8. ") == 1 and "\n11. " in prompting.SYSTEM_PROMPT_BASE)

    # ComfyUI köprüsü: hatalar 500 değil anlaşılır 502 olmalı.
    r = client.post("/api/comfyui/checkpoints", json={"url": MOCK_URL})  # 404 döner (ComfyUI değil)
    check("ComfyUI HTTP hatası -> 502 + ipucu (500 değil)",
          r.status_code == 502 and r.json()["detail"].get("hint"), r.text[:200])
    r = client.post("/api/comfyui/checkpoints", json={"url": "http://127.0.0.1:9"})
    check("ComfyUI kapalı -> 502", r.status_code == 502)

    out = client.post("/api/comfyui/send", json={
        "url": COMFY_URL, "checkpoint": "sdxl_base.safetensors", "positive": "p", "negative": "",
        "width": 768, "height": 1344, "steps": 24, "cfg": 1.0, "sampler": "euler",
        "scheduler": "simple", "seed": 0})
    last = httpx.get(f"{COMFY_URL}/_last", trust_env=False).json()
    check("ComfyUI: seed=0 korunuyor (rastgeleye dönmüyor)",
          out.status_code == 200 and out.json()["seed"] == 0 and last["3"]["inputs"]["seed"] == 0,
          out.text[:200])


def run_feature_checks(client):
    """Yeni özellikler: kalıcı oturumlar (SQLite), istek iptali, LoRA workflow'u."""
    store = get_store()

    # ---------------- Kalıcı oturumlar ----------------
    print("\n[S] Oturumların kalıcı saklanması (SQLite)")
    r1 = chat(client, "Miku duvar kağıdı", "phone", "sdxl")
    sid = r1["session_id"]
    r2 = chat(client, "var, trigger: mikuv2", "phone", "sdxl", session_id=sid)
    check("ikinci tur geçmişi SQLite'tan okuyup devam etti", r2["type"] == "package"
          and r2["package"]["lora"]["trigger"] == "mikuv2")
    listed = client.get("/api/sessions").json()["sessions"]
    mine = next((x for x in listed if x["id"] == sid), None)
    check("oturum listesinde başlık + aile/format + mesaj sayısı",
          mine is not None and mine["title"] == "Miku duvar kağıdı"
          and mine["family_id"] == "sdxl" and mine["format_id"] == "phone"
          and mine["message_count"] == 4, str(mine))
    check("liste en son güncellenen önce", listed[0]["id"] == sid)
    full = client.get(f"/api/sessions/{sid}").json()
    kinds = [(m["role"], m["kind"]) for m in full["messages"]]
    check("arayüz mesajları geri yüklenebiliyor (soru + paket)",
          kinds == [("user", "chat"), ("assistant", "chat"), ("user", "chat"), ("assistant", "package")],
          str(kinds))
    check("paket birebir saklandı",
          full["messages"][-1]["pkg"]["template_text"] == r2["package"]["template_text"])

    # Sunucu yeniden başlatılmış gibi: aynı dosyayı yeni bir bağlantıyla aç.
    reopened = SessionStore(DB_PATH)
    hist = reopened.history(sid, 100)
    check("yeniden açılan veritabanında geçmiş duruyor (restart sonrası)",
          len(hist) == 4 and hist[0]["content"] == "Miku duvar kağıdı")
    reopened.close()

    img_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    ri = client.post("/api/chat", json={"message": "", "image": "data:image/png;base64," + img_b64,
                                        "format_id": "phone", "family_id": "flux"}).json()
    gi = client.get(f"/api/sessions/{ri['session_id']}").json()
    check("görselli tur: görsel + başlık saklandı",
          gi["messages"][0].get("image", "").startswith("data:image/png;base64,")
          and gi["title"] == "Görselden prompt")
    check("LLM geçmişinde görsel analizi tarifi var (takip mesajları için)",
          "[Eklenen görselin otomatik analizi]" in store.history(ri["session_id"], 10)[0]["content"])

    d = client.delete(f"/api/sessions/{sid}").json()
    check("oturum silinebiliyor", d["deleted"] and client.get(f"/api/sessions/{sid}").status_code == 404)
    check("bilinmeyen/geçersiz oturum -> 404", client.get("/api/sessions/..%2Fetc").status_code == 404)

    small = SessionStore(":memory:", max_sessions=3)
    for i in range(5):
        small.append_turn(f"s{i}", "u", "a", {"kind": "chat"}, {"kind": "chat"}, "t", "phone", "sdxl")
    check("en eski oturumlar max_sessions sınırında budanıyor",
          small.count() == 3 and small.get("s0") is None and small.get("s4") is not None)
    small.close()

    # ---------------- İptal ----------------
    print("\n[C] Uzun süren isteği iptal etme")
    before = store.count()
    box = {}

    def slow():
        t0 = time.time()
        box["resp"] = client.post("/api/chat", json={
            "message": "yavaş bir orman", "format_id": "phone", "family_id": "sdxl",
            "request_id": "iptal-testi-1"})
        box["elapsed"] = time.time() - t0

    th = threading.Thread(target=slow)
    th.start()
    cancelled = False
    for _ in range(40):  # istek sunucuya ulaşıp kaydolana kadar dene
        time.sleep(0.1)
        cancelled = client.post("/api/chat/cancel", json={"request_id": "iptal-testi-1"}).json()["cancelled"]
        if cancelled:
            break
    th.join(timeout=15)
    resp = box.get("resp")
    check("iptal ucu sürmekte olan isteği buldu", cancelled)
    check("iptal edilen istek hızla 499 'cancelled' döndü (30 sn beklemedi)",
          resp is not None and resp.status_code == 499
          and resp.json()["detail"]["code"] == "cancelled" and box["elapsed"] < 10,
          f"{getattr(resp, 'status_code', None)} {box.get('elapsed')}")
    check("iptal edilen istek oturum/geçmiş bırakmadı", store.count() == before)
    nope = client.post("/api/chat/cancel", json={"request_id": "olmayan-istek"}).json()
    check("bilinmeyen request_id -> cancelled=false", nope == {"ok": True, "cancelled": False})
    ok = chat(client, "orman", "phone", "sdxl")
    check("iptalden sonra normal istekler çalışıyor", ok["type"] == "package")

    # ---------------- LoRA workflow ----------------
    print("\n[L] LoRA düğümlü ComfyUI workflow'u")
    lr = client.post("/api/comfyui/loras", json={"url": COMFY_URL})
    check("LoRA listesi ComfyUI'den çekiliyor",
          lr.status_code == 200 and "characters/miku_v2.safetensors" in lr.json()["loras"], lr.text[:200])
    base = {"url": COMFY_URL, "checkpoint": "sdxl_base.safetensors", "positive": "mikuv2, girl",
            "negative": "blurry", "width": 768, "height": 1344, "steps": 28, "cfg": 6.0,
            "sampler": "dpmpp_2m", "scheduler": "karras"}
    sr = client.post("/api/comfyui/send", json={
        **base, "lora": {"name": "characters/miku_v2.safetensors", "strength_model": 0.7}})
    wf = httpx.get(f"{COMFY_URL}/_last", trust_env=False).json()
    ln = wf.get("10", {})
    check("LoRA'lı gönderim kabul edildi", sr.status_code == 200 and sr.json()["lora"] == "characters/miku_v2.safetensors",
          sr.text[:200])
    check("workflow'da LoraLoader düğümü + dosya + ağırlıklar",
          ln.get("class_type") == "LoraLoader"
          and ln["inputs"]["lora_name"] == "characters/miku_v2.safetensors"
          and ln["inputs"]["strength_model"] == 0.7 and ln["inputs"]["strength_clip"] == 0.7)
    check("KSampler modeli ve iki CLIPTextEncode LoRA'dan besleniyor",
          wf["3"]["inputs"]["model"] == ["10", 0]
          and wf["6"]["inputs"]["clip"] == ["10", 1] and wf["7"]["inputs"]["clip"] == ["10", 1]
          and ln["inputs"]["model"] == ["4", 0] and ln["inputs"]["clip"] == ["4", 1])
    plain = client.post("/api/comfyui/send", json=base)
    wf2 = httpx.get(f"{COMFY_URL}/_last", trust_env=False).json()
    check("LoRA'sız gönderimde LoraLoader yok", plain.status_code == 200 and "10" not in wf2
          and wf2["3"]["inputs"]["model"] == ["4", 0])
    bad = client.post("/api/comfyui/send", json={**base, "lora": {"name": "yok.safetensors"}})
    check("sunucuda olmayan LoRA -> 502 + LoRA ipucu",
          bad.status_code == 502 and "LoRA" in (bad.json()["detail"].get("hint") or ""), bad.text[:200])
    inv = client.post("/api/comfyui/send", json={**base, "lora": {"name": "x", "strength_model": 99}})
    check("geçersiz LoRA ağırlığı -> 422", inv.status_code == 422)

    fmts, fams = load_presets()
    pkg = prompting.build_package(fmts["phone"], fams["sdxl"], {
        "positive": "girl singing on stage",
        "lora": {"name": "miku_v2.safetensors", "trigger": "mikuv2", "weight": 0.8}})
    check("guard: LLM unuttuysa LoRA tetikleyicisi başa ekleniyor",
          pkg["positive"].startswith("mikuv2, girl singing"))
    pkg = prompting.build_package(fmts["phone"], fams["sdxl"], {
        "positive": "a girl, MikuV2 style",
        "lora": {"name": "m", "trigger": "mikuv2", "weight": 0.8}})
    check("guard: tetikleyici zaten varsa tekrar eklenmiyor", pkg["positive"] == "a girl, MikuV2 style")


def load_presets():
    from backend import presets
    formats = presets.load_formats()
    families, _ = presets.load_families()
    return formats, families


if __name__ == "__main__":
    main()
