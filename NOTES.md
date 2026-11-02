# Geliştirme Notları (karar günlüğü)

Bu dosya, projeyi devralan birinin (veya bir sonraki oturumun) kararların *nedenini* hızlıca anlaması içindir.

## Mimari kararlar

1. **Backend: FastAPI (Python), Express değil.** Hedef kullanıcı ComfyUI kullanıyor → makinesinde Python zaten var. Node.js bağımlılığını tamamen kaldırmak için frontend önceden derlendi ve `frontend/dist` olarak teslim edildi; FastAPI bunu statik sunar. Kullanıcı için tek gereksinim: Python + Ollama.

2. **"Deterministik çekirdek + LLM protokolü" tasarımı (en kritik karar).** Yerel küçük modeller katı format kurallarına güvenilir uymaz. Bu yüzden LLM'den Bölüm 6 şablonunu yazması İSTENMEZ; yalnızca iki tip JSON döndürür: `{"action":"chat","message":…}` veya `{"action":"generate","positive_prompt":…,"negative_prompt":…,"lora":…,"note":…}`. Şablonu, çözünürlüğü, sampler/steps/CFG'yi backend `presets/*.json`'dan doldurur (`backend/prompting.py: build_package + render_template`). Sonuç: kabul kriterleri 2 (preset→çözünürlük), 3 (Flux'ta negative yasağı) ve 4 (şablona birebir uyum) **kod garantisi** altındadır; model kalitesinden bağımsızdır. Bölüm 5'teki sistem promptu metni birebir gömülü, yalnızca çıktı kanalı bu protokole bağlandı (6. kuralın şablonunu uygulama üretiyor — niyet korunuyor).

3. **Ollama entegrasyonu:** native `/api/chat` + structured outputs (JSON şeması ile `format`). Eski Ollama sürümü şemayı reddederse otomatik `format:"json"` → serbest metin kademeli düşüşü var; ayrıştırıcı (`parse_llm_output`) `<think>` blokları, ```json çitleri ve JSON etrafındaki lafları tolere eder, hiç JSON yoksa sohbet mesajına düşer (uygulama asla çökmez). `llm.mode:"openai"` ile LM Studio/llama.cpp de destekleniyor.

4. **SD 1.5 için ayrı taban çözünürlük (`gen_sd15`).** Görevdeki tablo yalnızca SDXL/Flux tabanı veriyor; SD 1.5'e 1344x768 vermek özne kopyalamasına yol açar. Her preset'e orana sadık, 8'in katı SD1.5 tabanı eklendi (ör. telefon 432x768). Aile hangi alanı kullanacağını `model_families.json → resolution_key` ile seçer.

5. **`trust_env=False` tüm yerel HTTP çağrılarında.** Sistem proxy'si tanımlı ortamlarda (kurumsal makineler dahil) httpx, localhost'a giden Ollama/ComfyUI isteklerini proxy'ye yönlendirip kırabiliyor — geliştirme sandbox'ında bizzat yaşandı. Yerel servislere proxy uygulanmaması doğru davranış.

6. **Avatar preset'i istisnası:** hedef (512) üretimden (1024) küçük olduğundan şablondaki etiket "Nihai hedef (downscale sonrası)" olarak uyarlanır; diğer tüm preset'lerde "upscale sonrası" yazar.

7. **ComfyUI gönderimi backend proxy'siyle** yapılır (tarayıcı→8188 CORS sorunu yok). Şablon: CheckpointLoaderSimple → CLIPTextEncode ×2 → KSampler → VAEDecode → SaveImage (`backend/workflows/`). Steps/CFG aralığın orta değeri, seed rastgele. **LoRA (v1.2):** ikinci bir şablon (`text2img_lora.json`) LoraLoader'ı checkpoint ile KSampler/CLIPTextEncode arasına yerleştirir (model ve CLIP ikisi de LoRA'dan geçer). İlk sürümde LoRA düğümü yoktu çünkü LLM'in önerdiği dosya adı sunucudaki gerçek dosyayla eşleşmeyebilir. Çözüm: dosya adı ASLA LLM'den alınmaz; `/object_info/LoraLoader` listesinden seçilir. LLM önerisi yalnızca arayüzde en yakın dosyayı ön-seçmek için kullanılır (`frontend/src/lora.js`, normalize edilmiş ad/tetikleyici eşleşmesi). Ek guard: paket bir LoRA tetikleyicisi içeriyorsa ama positive prompt'ta yoksa backend tetikleyiciyi başa ekler.

8. **Oturumlar SQLite'ta kalıcı (v1.2, `backend/sessions.py`).** İlk sürüm in-memory idi. Artık standart kütüphane `sqlite3` kullanılıyor; ek bağımlılık yok, WAL modu açık. Her mesaj satırı iki şey taşır: LLM'e geri gönderilen `content` (görsel tarifi dahil, `<think>` hariç) ve arayüzü yeniden çizmek için `ui` JSON'u (kullanıcının asıl metni, küçültülmüş görsel, prompt paketi). Böylece geçmişten açılan bir sohbet hem görsel olarak birebir geri gelir hem de LLM bağlamıyla devam eder. Bir tur yalnızca başarıyla bittiğinde **atomik olarak** yazılır: iptal edilen ya da hata alan istekler boş oturum veya yarım tur bırakmaz. Son 24 mesaj LLM'e gönderilir. `max_sessions` (500) üstündeki en eski oturumlar budanır. "Yeni sohbet" artık sunucudaki oturumu silmez; silme geçmiş çekmecesinden yapılır (`DELETE /api/sessions/{id}`). Testler `SESSIONS_DB` ile geçici bir dosya kullanır.

9. **Faz 2 özellikleri dahil edildi** (mimari zaten hazırdı, maliyeti düşüktü): ComfyUI'ye gönderme, favoriler (tarayıcı localStorage), stil kütüphanesi (`presets/styles.json`). Frontend'de `llm_guidance` istemciye sızdırılmaz.

10. **Görselden prompt tahmini: iki aşamalı vision akışı (v1.1).** Görsel, ayrı bir çok-modlu modelle (`llm.vision_model`, varsayılan qwen2.5vl:7b) tek paragraflık İngilizce tarife çevrilir; tarif "[Eklenen görselin otomatik analizi]: …" bloğu olarak kullanıcı mesajına gömülür ve NORMAL metin boru hattından geçer. Tek modelli (vision modeliyle sohbet) alternatife tercih edilme nedenleri: (a) sohbet geçmişi salt metin kalır — takip mesajları ("aynısı ama gece") görsel olmadan çalışır, model yönlendirme karmaşası yok; (b) kullanıcı sohbet modelini serbestçe seçebilir, görsel desteklemeyen modellerle çakışma olmaz; (c) iki model VRAM'de aynı anda durmak zorunda değil (keep_alive sırayla boşaltır; "Belleği boşalt" artık ikisini de kaldırır). Görsel tarayıcıda ~1024px JPEG'e küçültülür (canvas), backend data-URL önekini ayıklar. Vision modeli yüklü değilse Türkçe hata + `ollama pull` ipucu döner.

11. **Yerel API güvenliği (kod incelemesi, 2026-11-02).** Backend, kullanıcının Ollama/ComfyUI'sine istek ileten bir proxy olduğu için "herkese açık" olmamalı. Önceden `CORS allow_origins=["*"]` vardı: kullanıcının açtığı herhangi bir web sitesi arka planda `/api/comfyui/send` ile kuyruğa iş ekleyebilir, `base_url` parametreleri üzerinden yerel ağa istek attırıp yanıtı okuyabilirdi. Arayüz aynı kökenden sunulduğundan CORS tamamen kapatıldı (`server.cors_origins` ile açıkça açılabilir) ve loopback'te Host başlığı izin listesi eklendi (DNS rebinding). Ayrıca girdi sınırları: mesaj ≤ 8000 karakter, görsel ≤ 16 MB base64 + geçerlilik kontrolü, oturum kimliği `[A-Za-z0-9_-]{1,64}`.

12. **Model "yüklü mü" kontrolü tam etiket eşleşmesi kullanır.** Eski kod yalnızca model adının kökünü (`qwen3`) karşılaştırıyordu; `qwen3:8b` yüklüyken `qwen3:14b` seçilse "yüklü" görünüyor, ilk istekte 404 alınıyordu. Ollama kuralına uygun olarak etiketsiz ad `:latest` sayılır.

13. **Ağ hataları tek noktada çevrilir.** `httpx.HTTPError`'ın tüm alt türleri (bağlantı, zaman aşımı, protokol) ve JSON olmayan yanıtlar Türkçe `LLMError`/`ComfyError`'a dönüştürülür — kullanıcı hiçbir durumda çıplak "500 Internal Server Error" görmez. Ollama 5xx (ör. bellek yetersiz) döndürürse ağır istek format kademeleriyle 3 kez tekrarlanmaz.

14. **İstek iptali (v1.2).** Tarayıcı her sohbet isteğine bir `request_id` ekler ve `AbortController` ile isteği keser. Backend tarafında LLM boru hattı (vision + chat) ayrı bir asyncio görevi olarak çalışır ve iki yoldan iptal edilir: (a) `POST /api/chat/cancel {request_id}`, (b) istemci bağlantısının kopması (`request.is_disconnected()` 0,5 sn'de bir yoklanır; proxy'ler bağlantıyı açık tutsa bile (a) çalışır). Görev iptal edilince httpx Ollama bağlantısını kapatır, Ollama da üretimi durdurur; bu, gerçek süreçlerle doğrulandı. İptal edilen istek 499 `cancelled` döner ve veritabanına hiçbir şey yazılmaz. Host koruması bu yüzden `BaseHTTPMiddleware` yerine saf ASGI ara katmanı olarak yazıldı (bağlantı kopma olayının uç noktaya ulaşmasını engellememesi için).

## Doğrulama (Bölüm 10 — 2026-07-02, v1.1 vision güncellemesiyle yeniden koşuldu)

`tests/test_acceptance.py`: sahte Ollama (`tests/mock_ollama.py`) gerçek HTTP sunucusu olarak koşturuldu; backend gerçek istek döngüsünden geçirildi. İlk sürümde **52/52 kontrol geçti** (güncel durum: 94 kontrol — v1.2'de güvenlik regresyonları, SQLite oturumları, iptal ve LoRA workflow'u eklendi; sahte ComfyUI `tests/mock_comfyui.py` workflow'u ve düğüm bağlantılarını doğrular):

- Kriter 1 (stil ayrımı): aynı "sisli orman" isteği 4 ailede farklı üretildi; pony `score_9…` ile, sd15 `masterpiece…` ile başlıyor, flux çok cümleli doğal dil; ailelere özel rehberin sistem promptuna enjekte edildiği ayrıca doğrulandı.
- Kriter 2 (çözünürlük): masaüstü 1344x768 ↔ telefon 768x1344; SD1.5 telefonda 432x768; avatar 1024→512 downscale etiketi.
- Kriter 3 (Flux): sahte model kasıtlı negative gönderdi → guard sildi, şablonda NEGATIVE bölümü yok, CFG "1.0 (FluxGuidance ≈ 3.5)".
- Kriter 4 (şablon): telefon+SDXL+LoRA paketi beklenen şablonla **karakter karaktere** eşleşti.
- Kriter 5 (karakter): "Hatsune Miku telefon duvar kağıdı" → önce LoRA sorusu; "yok"+Pony → `hatsune_miku, vocaloid` etiketi; "yok"+SDXL → isimsiz tarif + LoRA önerisi notu; trigger verilince → trigger başta + LoRA satırı şablonda.
- Görselden prompt [6]: boş metin + görsel → paket; sahte vision tarifi ikinci aşamada aile stiline çevrildi (flux doğal dil / pony score_9 booru); görsel akışında da Flux negative guard'ı ve preset çözünürlüğü doğrulandı; data-URL öneki ayıklanıyor; vision modeli yoksa 502 + `ollama pull` ipucu; status ucu vision bilgisi raporluyor.
- Ek: bozuk model çıktısı sohbete düşer, Ollama kapalıyken 502+Türkçe ipucu, geçersiz preset 400, çözünürlükler 8'in katı, aile seçilmezse varsayılan SDXL.

Ayrıca gerçek süreçle (`python -m backend.main`) frontend'in sunulduğu ve story+flux isteğinin doğru paket ürettiği doğrulandı.

**Sınır:** Geliştirme ortamının ağ kısıtları nedeniyle gerçek bir LLM indirilemedi; kabul kriterlerinin LLM'den bağımsız olanları kod garantisiyle, LLM'e bakan uçlar sahte-model boru hattıyla test edildi. Gerçek modelle uçtan uca gözlem için kullanıcı makinesinde: `python tests/live_smoke.py` (5 senaryo, kural kontrolleri otomatik).

## Bilinen küçük kararlar

- `phone_hd` preset'i tabloya sadık kalarak oran "9:16" etiketiyle 1440x3120 hedefler (gerçek oran 9:19.5'tir; tablo verisi korundu).
- Varsayılan port 8765 (8188=ComfyUI ve 11434=Ollama ile çakışmasın diye).
- Pony rehberi hem `score_9…` (Pony) hem `masterpiece, best quality` (Illustrious) kalite bloklarını öğretir — iki checkpoint türünde de güvenli.
- `frontend/dist` her zaman tek bir güncel build içerir; `index.html` hash'li dosya adlarıyla eşleşmelidir. Arayüzü değiştirip yeniden derlerseniz eski hash'li dosyaları silmek yeterlidir.
- Hedef çözünürlük üretim çözünürlüğüne eşitse (ör. SD 1.5 + avatar, 512→512) şablon etiketi "ölçekleme gerekmez" olur; yanlışlıkla "upscale sonrası" yazılmaz.
- ComfyUI gönderiminde `seed: 0` geçerli bir değer olarak korunur; yalnızca seed verilmediğinde rastgele seçilir.
- Başlatıcılar bağımlılıkları proje içi `.venv`'e kurar (PEP 668 nedeniyle sistem `pip install` birçok Linux/macOS kurulumunda reddediliyor).
