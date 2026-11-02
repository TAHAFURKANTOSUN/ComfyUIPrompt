<div align="center">

# 🎨 ComfyUI Prompt Asistanı

**Doğal dilden ComfyUI'ye hazır prompt paketi — tamamen yerel, API anahtarı yok.**

Türkçe fikir → 🧠 yerel LLM → 📋 hazır prompt paketi → 🖱️ ComfyUI

![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-lightgrey.svg)
![Local](https://img.shields.io/badge/%25100-yerel%20%2F%20local-success.svg)

</div>

---

Doğal dilde anlattığınız fikri ("sisli bir orman, gizemli atmosfer"), seçtiğiniz **format preset'i** ve **model ailesine** göre ComfyUI'de doğrudan kullanılabilir bir prompt paketine çevirir: positive prompt, negative prompt, üretim çözünürlüğü ve sampler ayarları — hepsi tek tık kopyalanabilir. Bir **görsel de yükleyebilirsiniz**: asistan görseli analiz edip benzerini üretecek prompt'u çıkarır. Tamamen yereldir; LLM olarak Ollama kullanır, API anahtarı gerekmez.

## ✨ Özellikler

- 🗣️ **Türkçe → İngilizce prompt** — fikrinizi Türkçe anlatın, ComfyUI'ye hazır İngilizce prompt paketi çıksın.
- 🎯 **Format preset'leri** — telefon, 4K masaüstü, Instagram vb. için üretim ve hedef çözünürlük otomatik ayarlanır.
- 🧬 **Model ailesine özel stil** — SD 1.5 / SDXL / Pony-Illustrious / Flux için tamamen farklı prompt yazım kuralları (etiket listesi ↔ doğal dil).
- 🖼️ **Görselden prompt çıkarma** — bir görsel yükleyin, benzerini üretecek prompt otomatik çıksın.
- 🎭 **Karakter + LoRA farkındalığı** — LoRA'nız varsa tetikleyici kelimeyi ve önerilen ağırlığı otomatik yerleştirir.
- 🔌 **ComfyUI'ye tek tık gönderim** — prompt'u kopyalamadan doğrudan üretim kuyruğuna ekler; LoRA seçerseniz workflow'a LoraLoader düğümü eklenir (opsiyonel).
- 🕘 **Kalıcı sohbet geçmişi** — sohbetler yerel bir SQLite dosyasında saklanır; sayfa yenilense ya da sunucu yeniden başlasa da kaldığınız yerden devam edersiniz.
- ⏹️ **İptal** — uzun süren bir isteği tek tıkla (ya da Esc ile) durdurun; yerel modeldeki üretim de hemen kesilir.
- 🔒 **%100 yerel** — LLM olarak Ollama kullanır; API anahtarı gerekmez, hiçbir veri dışarı çıkmaz.

## 📋 İçindekiler

- [📦 Gereksinimler](#-gereksinimler)
- [🚀 Kurulum (3 adım)](#-kurulum-3-adım)
- [🎨 Kullanım](#-kullanım)
  - [🖼️ Görselden prompt tahmini](#-görselden-prompt-tahmini)
  - [🎭 Karakter istekleri](#-karakter-istekleri)
  - [🕘 Geçmiş sohbetler ve iptal](#-geçmiş-sohbetler-ve-iptal)
- [💾 VRAM paylaşımı](#-vram-paylaşımı-comfyui--llm-aynı-gpuda)
- [🔌 ComfyUI'ye doğrudan gönderme](#-comfyuiye-doğrudan-gönderme-opsiyonel)
- [⚙️ Yapılandırma](#-yapılandırma)
- [✅ Testler](#-testler)
- [🐛 Sorun giderme](#-sorun-giderme)
- [📁 Proje yapısı](#-proje-yapısı)
- [🤝 Katkıda bulunma](#-katkıda-bulunma)
- [📄 Lisans](#-lisans)

---

## 📦 Gereksinimler

Python 3.10+ ve [Ollama](https://ollama.com) yeterlidir. Node.js **gerekmez** — arayüz derlenmiş halde (`frontend/dist`) hazır gelir.

## 🚀 Kurulum (3 adım)

1. **Ollama'yı kurun** (ollama.com) ve bir model indirin. GPU belleğinize göre öneri:

   | GPU VRAM (ComfyUI ile paylaşımlı) | Model | Komut |
   |---|---|---|
   | 8 GB ve altı | Qwen3 8B | `ollama pull qwen3:8b` |
   | 12–16 GB | Qwen3 14B | `ollama pull qwen3:14b` |
   | 16 GB+ veya CPU/RAM'de | Qwen3 30B-A3B (MoE) | `ollama pull qwen3:30b-a3b` |

   Görselden prompt tahmini de kullanacaksanız bir de çok-modlu (vision) model indirin:
   `ollama pull qwen2.5vl:7b` (8 GB altı VRAM için: `ollama pull qwen2.5vl:3b`).

2. **`start.bat`'a çift tıklayın** (Windows) ya da `./start.sh` çalıştırın (Linux/macOS). İlk açılışta proje klasöründe bir `.venv` sanal ortamı oluşturup Python bağımlılıklarını oraya kurar (sistem Python'unuza dokunmaz; yeni Debian/Ubuntu/Homebrew sürümlerindeki "externally-managed-environment" hatası da böylece yaşanmaz).

3. Tarayıcıda **http://127.0.0.1:8765** adresini açın.

> 💡 Varsayılan model `qwen3:8b`'dir. Farklı bir model indirdiyseniz arayüzdeki **Ayarlar**'dan seçin veya `config.json` içindeki `llm.model` alanını değiştirin.

## 🎨 Kullanım

1. Üstteki butonlardan **format** seçin (telefon, 4K masaüstü, Instagram…) — üretim ve hedef çözünürlüğü otomatik belirlenir.
2. Açılır menüden **model ailesini** seçin (SD 1.5 / SDXL / Pony-Illustrious / Flux) — prompt yazım stili buna göre kökten değişir (etiket listesi ↔ doğal dil).
3. İsteğinizi Türkçe yazın. Bilgi eksikse asistan en fazla 2–3 kısa soru sorar; yeterliyse doğrudan üretir. Prompt çıktıları her zaman **İngilizce** üretilir.
4. Çıkan kartta her blok için ayrı **Kopyala** butonu vardır: positive → `CLIPTextEncode (positive)`, negative → `CLIPTextEncode (negative)`, çözünürlük → `EmptyLatentImage`, sampler/steps/cfg → `KSampler`.

### 🖼️ Görselden prompt tahmini

Yazma alanındaki resim simgesine tıklayarak (ya da panodan yapıştırarak / sürükleyip bırakarak) bir görsel ekleyin. Görsel önce yerel vision modeliyle ayrıntılı bir İngilizce tarife çevrilir, sonra bu tarif seçili format ve model ailesinin stilinde bir prompt paketine dönüştürülür. Görselin yanına "ama gece olsun" gibi değişiklik notu da yazabilirsiniz; boş bırakırsanız görselin benzerini üretecek prompt çıkar. Görsel tarayıcıda ~1024px'e küçültülerek gönderilir, hiçbir yere yüklenmez — her şey yerelde kalır.

### 🎭 Karakter istekleri

"Hatsune Miku duvar kağıdı" gibi isteklerde asistan önce o karakter için LoRA'nız olup olmadığını sorar. LoRA varsa tetikleyici kelimesini prompt'a yerleştirir ve önerilen ağırlığı belirtir; yoksa Pony/Illustrious'ta karakter+seri etiketini doğrudan kullanır, SDXL/Flux'ta ise ismi değil karakterin görsel tarifini yazar (bu modeller isimleri güvenilir tanımaz). Palet simgesinden hazır **stil çipleri**, yıldız simgesinden **favoriler** kullanılabilir.

### 🕘 Geçmiş sohbetler ve iptal

- Her sohbet otomatik olarak `data/sessions.db` (SQLite) dosyasına kaydedilir. Üst bardaki **saat** simgesi geçmiş sohbetleri listeler; birine tıklayınca mesajlar, prompt kartları ve o sohbetin format/model ailesi seçimi geri gelir ve sohbete kaldığınız yerden devam edebilirsiniz. Çöp kutusu simgesi sohbeti kalıcı olarak siler.
- Sayfayı yenilediğinizde son açık sohbet otomatik geri yüklenir. **Yeni sohbet** düğmesi eski sohbeti silmez, yalnızca yenisini başlatır.
- Eklediğiniz görseller de (küçültülmüş hâliyle) sohbetle birlikte saklanır. Veriler yalnızca bu bilgisayarda durur; tamamen silmek için `data/` klasörünü silebilirsiniz.
- Bir istek uzun sürüyorsa "Prompt hazırlanıyor…" balonundaki **İptal** düğmesine, kırmızı durdur düğmesine ya da **Esc**'ye basın. Backend LLM isteğini keser (Ollama'daki üretim de durur, GPU boşa çalışmaz); yazdığınız mesaj ve görsel düzenlemeniz için yazma alanına geri konur. İptal edilen istekler geçmişte iz bırakmaz.

## 💾 VRAM paylaşımı (ComfyUI + LLM aynı GPU'da)

- LLM sohbeti bittikten 5 dakika sonra bellekten düşer (`config.json` → `llm.keep_alive`).
- Görsel üretimine başlamadan önce **Ayarlar → Belleği boşalt (VRAM)** düğmesiyle LLM'i anında bellekten atabilirsiniz.
- Alternatif: MoE modelini (qwen3:30b-a3b) CPU/RAM'de çalıştırıp GPU'yu tamamen ComfyUI'ye bırakın.

## 🔌 ComfyUI'ye doğrudan gönderme (opsiyonel)

**Ayarlar → ComfyUI** bölümüne sunucu adresinizi yazın (ör. `http://127.0.0.1:8188`), **Bağlan** ile checkpoint listesini çekip birini seçin. Artık her prompt kartındaki **ComfyUI'ye Gönder** butonu, üretimi basit bir text2img workflow'uyla (checkpoint → prompt → KSampler → kaydet) doğrudan kuyruğa ekler. İstekler backend üzerinden iletildiği için ComfyUI'de CORS ayarı gerekmez. (Flux'un tek dosyalık fp8 checkpoint'leri de bu workflow'la çalışır; CFG otomatik 1.0 gönderilir.)

**LoRA'lı gönderim:** **Bağlan** checkpoint'lerle birlikte sunucudaki LoRA dosyalarını da çeker. Her prompt kartında bir **ComfyUI LoRA** seçimi belirir. Asistan bir LoRA önerdiyse (ör. `miku_v2.safetensors` / tetikleyici `mikuv2`), sunucudaki en yakın dosya (ör. `characters/miku_v2.safetensors`) otomatik seçilir ve önerilen ağırlık doldurulur. İsterseniz başka bir dosya ya da "LoRA'sız gönder" seçebilirsiniz. LoRA seçiliyse `backend/workflows/text2img_lora.json` kullanılır: checkpoint → **LoraLoader** (model + CLIP) → prompt → KSampler → kaydet. LoRA'nın tetikleyici kelimesi positive prompt'ta yoksa asistan onu otomatik olarak başa ekler.

## ⚙️ Yapılandırma

- **`config.json`** — LLM adresi/modeli, görsel analizi için `vision_model`, `keep_alive`, zaman aşımı, sunucu portu, sohbet veritabanı (`sessions.db_path`, varsayılan `data/sessions.db`; `":memory:"` kalıcı olmayan mod) ve saklanacak en fazla sohbet sayısı (`sessions.max_sessions`, varsayılan 500 — en eskiler otomatik silinir). `llm.mode` alanını `"openai"` yaparak LM Studio / llama.cpp server gibi OpenAI-uyumlu yerel sunuculara da bağlanabilirsiniz (vision dahil).
- **`presets/formats.json`** — format preset'leri. Yeni bir satır ekleyerek (id, ad, oran, `target`, `gen`, `gen_sd15`, ikon) kod değişikliği olmadan yeni preset tanımlayabilirsiniz; sunucuyu yeniden başlatmak bile gerekmez. Arayüzde ilk seçili gelen preset `default` alanıyla belirlenir.
- **`presets/model_families.json`** — model aileleri, sampler/steps/cfg varsayılanları ve her ailenin prompt stili rehberi (`llm_guidance`).
- **`presets/styles.json`** — stil kütüphanesi çipleri.

**Ortam değişkenleri** (`config.json`'u ezer): `OLLAMA_BASE_URL` / `LLM_BASE_URL`, `LLM_MODEL`, `LLM_VISION_MODEL`, `LLM_MODE`, `HOST`, `PORT`, `SESSIONS_DB`.

### 🔐 Güvenlik ve ağdan erişim

Sunucu varsayılan olarak yalnızca `127.0.0.1`'i dinler ve iki koruma uygular:

- **CORS kapalıdır** (`server.cors_origins: []`): arayüz zaten aynı adresten sunulduğu için gerekmez. Böylece tarayıcıda açtığınız başka bir web sitesi bu yerel API üzerinden Ollama'nıza/ComfyUI'nize istek gönderemez.
- **Host başlığı kontrolü** (`server.allowed_hosts`): DNS rebinding saldırılarına karşı yalnızca `127.0.0.1`, `localhost`, `::1` kabul edilir.

Arayüzü telefon/başka bir bilgisayardan açmak isterseniz `server.host`'u `"0.0.0.0"` yapın (bu durumda Host kontrolü uygulanmaz; yalnızca güvendiğiniz ağlarda kullanın). Uygulamada kimlik doğrulama yoktur.

SD 1.5 için tabloya ek olarak ayrı bir taban çözünürlük (`gen_sd15`) tutulur; SD 1.5, SDXL tabanı olan ~1344px'te özne kopyalama yaptığı için asistan bu ailede otomatik olarak 512–768px tabanına iner ve hedefe upscale önerir.

## ✅ Testler

- `python tests/test_acceptance.py` — sahte bir Ollama sunucusuyla tüm kabul kriterlerini uçtan uca doğrular (görselden-prompt akışı, güvenlik/sağlamlık regresyonları, kalıcı oturumlar, istek iptali ve LoRA workflow'u dahil 94 kontrol; gerçek model gerektirmez). Sahte Ollama ve sahte ComfyUI (`tests/mock_comfyui.py`) boş portlarda açılır, oturumlar geçici bir veritabanına yazılır — makinenizdeki gerçek Ollama'yla ya da sohbet geçmişinizle çakışmaz.
- Her push/PR'da GitHub Actions bu testleri (Python 3.10 ve 3.13) ve frontend build'ini otomatik çalıştırır (`.github/workflows/tests.yml`).
- `python tests/live_smoke.py` — gerçek Ollama'yla 5 canlı senaryo koşturur (önce `python -m backend.main` ile sunucuyu açın). `--image bir_resim.jpg` ile görselden-prompt senaryosu da eklenir.

## 🐛 Sorun giderme

- **"Ollama'ya ulaşılamıyor"** — Ollama kurulu ve açık mı? Terminalde `ollama serve` deneyin; adres farklıysa Ayarlar'dan düzeltin.
- **"... modeli Ollama'da yüklü değil"** — Hata mesajındaki `ollama pull …` komutunu çalıştırın.
- **"Görsel analizi için '…' modeli yüklü değil"** — Vision modelini indirin: `ollama pull qwen2.5vl:7b`, ya da Ayarlar'dan yüklü çok-modlu bir model seçin.
- **Port 8765 dolu** — `config.json` → `server.port` değerini değiştirin.
- **"Geçersiz Host başlığı"** — Arayüzü `127.0.0.1`/`localhost` dışında bir adla açıyorsunuz; adı `config.json` → `server.allowed_hosts` listesine ekleyin.
- **`./start.sh: Permission denied`** — `chmod +x start.sh` çalıştırın ya da `bash start.sh` ile başlatın.
- **Arayüzü değiştirmek istiyorum** — Kaynak `frontend/src` içindedir; Node.js kurup `cd frontend && npm ci && npm run build` ile yeniden derleyin (yalnızca geliştirme için gerekir). Geliştirme sırasında `npm run dev` (Vite, `/api` isteklerini 8765'e yönlendirir) kullanılabilir.

## 📁 Proje yapısı

```
├─ start.bat / start.sh      → tek tıkla başlat
├─ config.json               → LLM ve sunucu ayarları
├─ presets/                  → format / model ailesi / stil config'leri (düzenlenebilir)
├─ backend/                  → FastAPI: LLM proxy'si, guard'lar, şablon, ComfyUI köprüsü, oturum deposu
│  └─ workflows/             → ComfyUI text2img workflow şablonları (düz + LoRA'lı)
├─ data/                     → sohbet geçmişi (sessions.db, otomatik oluşur, git'e girmez)
├─ frontend/                 → React + Tailwind kaynak kodu ve hazır build (dist/)
└─ tests/                    → kabul testleri (mock Ollama + mock ComfyUI) + canlı duman testi
```

---

## 🤝 Katkıda bulunma

Hata bildirimi ve öneriler için Issues bölümü kullanılabilir. Pull request göndermeden önce büyük değişiklikler için önce bir issue açıp konuşulması önerilir. Kod üzerinde çalışırken:

- Mimari kararların gerekçesi için önce `NOTES.md`'ye bakın — özellikle "deterministik çekirdek + LLM protokolü" ayrımı (bkz. madde 2) LLM'in şablon/çözünürlük/sampler değerlerini asla doğrudan üretmediğini, bunların `presets/*.json`'dan geldiğini garanti eder; bu ayrımı bozmayan değişiklikler tercih edilir.
- Frontend değişiklikleri `frontend/src` içinde yapılıp `npm run build` ile `frontend/dist` güncellenmelidir (derlenmiş çıktı repoya dahildir). Bağımlılık sürümleri `frontend/package-lock.json` ile sabitlenmiştir; `npm install` yerine `npm ci` kullanın.
- Göndermeden önce `python tests/test_acceptance.py`'nin 94 kontrolü de geçtiğinden emin olun; davranışı değiştiren PR'larda ilgili teste de bir kontrol eklenmesi beklenir.

## 📄 Lisans

MIT lisansı ile sunulmaktadır — ayrıntılar için [LICENSE](LICENSE) dosyasına bakın.
