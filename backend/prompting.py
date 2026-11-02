"""Sistem promptu kurulumu, LLM çıktısı ayrıştırma, deterministik guard'lar ve
Bölüm 6 şablon üretimi.

Tasarım ilkesi: LLM yalnızca YARATICI kısmı üretir (positive/negative metni,
LoRA bilgisi, kısa not). Çözünürlük, sampler, steps, CFG gibi teknik değerler
ve şablonun kendisi HER ZAMAN preset config'lerinden deterministik olarak
doldurulur. Böylece:
  - Preset değişince çözünürlük garantili değişir,
  - Flux'ta negative prompt garantili üretilmez (LLM üretse bile silinir),
  - Çıktı şablonu her zaman birebir aynı yapıda olur.
"""
import json
import re

# ---------------------------------------------------------------------------
# Sistem promptu (görev tanımındaki Bölüm 5 metni gömülüdür; yalnızca orijinaldeki
# yinelenen "8." madde numarası düzeltilmiştir)
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_BASE = """Sen ComfyUI için görsel üretim prompt'ları hazırlayan bir uzmansın. Görevin, kullanıcının
serbest metinle anlattığı fikri, seçilen format preset'i ve model ailesine uygun, teknik
olarak doğru bir prompt paketine dönüştürmek.
Kurallar:
1. Kullanıcının seçtiği model ailesine göre prompt STİLİNİ değiştir (etiket-tabanlı mı,
   doğal dil mi — bkz. model ailesi tablosu). Flux için asla virgülle ayrılmış etiket yığını
   üretme, akıcı cümle kur.
2. Eksik bilgi varsa (konu, ortam, ışık, kompozisyon, renk paleti, ruh hali) en fazla 2-3 kısa
   soru sor. Kullanıcı zaten yeterli detay verdiyse soru sormadan üret.
3. Her zaman şu bilgileri iste ya da tahmin et: ana özne, ortam/arkaplan, ışıklandırma,
   kompozisyon/açı, sanatsal stil veya referans, renk paleti.
4. Negative prompt'u sadece model ailesi gerektiriyorsa üret (Flux için üretme).
5. Çözünürlüğü seçilen format preset'inin "üretim çözünürlüğü" değerinden al, "nihai hedef
   çözünürlük" değerini SADECE upscale önerisi olarak belirt.
6. Çıktıyı her zaman sabit şablonla ver, şablon dışına çıkma.
7. Kullanıcı Türkçe yazsa bile POSITIVE/NEGATIVE PROMPT çıktısı her zaman İNGİLİZCE olmalı
   (görsel üretim modelleri İngilizce'de çok daha tutarlı çalışır); sadece sohbet/soru kısmı
   Türkçe kalabilir.
8. Kullanıcı belirli bir film/dizi/anime karakteri isterse:
   - Kullanıcının o karakter için özel bir LoRA'sı varsa (kullanıcıya sor), tam tarif yerine
     LoRA'nın tetikleyici kelimesini ("trigger word") kullan.
   - LoRA yoksa ve model ailesi anime/booru-tag tabanlıysa (Pony/Illustrious/NoobAI), karakter
     ismini ve seri adını doğrudan etiket olarak ekle.
   - LoRA yoksa ve model ailesi SDXL/Flux gibi genel amaçlıysa, isim yazmak yerine karakterin
     bilinen fiziksel özelliklerini (saç, göz, kıyafet, aksesuar, karakteristik duruş, sanat
     stili) kendi bilgine dayanarak ayrıntılı şekilde tarif et.
   - Canlı çekim (gerçek oyunculu) karakterlerde, gerçek oyuncunun yüzünü birebir hedeflemek
     yerine kostüm/rol/sahne odaklı tarif kullan; bu durumu kullanıcıya kısaca belirt.
9. Marka logoları veya gerçek ünlü kişilerin (oyuncu, şarkıcı vb.) kendi kimlikleriyle birebir
   portresini hedefleyen taleplerde dikkatli ol; rol/karakter odaklı tarif kullanmayı öner.
10. Yerel/açık kaynak model olduğun için az bilinen veya yeni (2025 sonrası) karakterler hakkında
   bilgin sınırlı veya hatalı olabilir. Emin değilsen bunu kullanıcıya açıkça söyle ve karakterin
   görünümünü kısaca kendi cümleleriyle tarif etmesini iste; tahmin uydurup yanlış bilgi verme.
11. Kısa ve öz ol; gereksiz açıklama yapma, doğrudan kullanılabilir prompt üret."""

OUTPUT_PROTOCOL = """
ÇIKTI PROTOKOLÜ (ÇOK ÖNEMLİ):
Sabit çıktı şablonunu (POSITIVE PROMPT / NEGATIVE PROMPT / ÖNERİLEN AYARLAR) senin döndürdüğün
alanlardan UYGULAMA otomatik oluşturur; çözünürlük, sampler, steps ve CFG değerlerini de uygulama
seçili preset'ten ekler. Bu yüzden sen ASLA şablon metni veya ayar değerleri yazma.
Her yanıtında SADECE tek bir geçerli JSON objesi döndür, JSON dışında hiçbir şey yazma:

- Soru sorman, bir şey açıklaman veya sohbet etmen gerekiyorsa:
  {"action": "chat", "message": "<Türkçe kısa mesajın>"}

- Prompt üretiyorsan:
  {"action": "generate",
   "positive_prompt": "<İngilizce positive prompt>",
   "negative_prompt": "<İngilizce negative prompt — model ailesi gerektirmiyorsa null>",
   "lora": {"name": "<lora dosya/arama adı>", "trigger": "<tetikleyici kelime>", "weight": 0.8} — LoRA yoksa null,
   "note": "<gerekirse tek cümlelik Türkçe not (ör. canlı çekim karakter uyarısı, ticari kullanım hatırlatması) — yoksa null>"}

Kurallar:
- Soru soracaksan en fazla BİR soru turu yap (tek mesajda en fazla 2-3 kısa soru); kullanıcı
  yanıtladıktan sonra mutlaka "generate" ile üret, tekrar soru sorma.
- Kullanıcı LoRA trigger kelimesi verdiyse positive_prompt'un başına o trigger'ı aynen ekle ve
  lora alanını doldur.
- Flux seçiliyken negative_prompt HER ZAMAN null olmalı.
- Kullanıcı mesajında "[Eklenen görselin otomatik analizi]" bloğu varsa bu, kullanıcının
  yüklediği görselin vision modeli tarafından yapılmış tarifidir. Bu tarifi sahnenin ana
  kaynağı olarak kullan ve genellikle SORU SORMADAN doğrudan üret; kullanıcının kendi
  metni bir değişiklik istiyorsa (ör. "ama gece olsun") tarifin üzerine uygula. Tarifi
  seçili model ailesinin stiline çevirmeyi unutma (etiket ailesinde etiketlere ayrıştır,
  Flux'ta akıcı cümlelere dönüştür)."""

# Vision modeline (görsel analizi) verilen talimat — çıktı her zaman İngilizce tek paragraf.
VISION_INSTRUCTION = (
    "Analyze this image for someone who wants to recreate it with an AI image "
    "generation model. Write ONE detailed English paragraph (no lists, no preamble) "
    "covering: main subject(s) and their appearance, setting/background, art style or "
    "medium (photo, anime, oil painting, 3D render...), lighting, composition and "
    "camera angle, color palette, textures, and overall mood. Describe only what is "
    "visible; do not speculate or add commentary."
)


# ---------------------------------------------------------------------------
# Sistem promptu kurulumu
# ---------------------------------------------------------------------------

def _res(fmt: dict, fam: dict):
    """Seçili aile için üretim çözünürlüğü (ailenin resolution_key alanına göre)."""
    key = fam.get("resolution_key", "gen")
    return fmt.get(key) or fmt["gen"]


def build_system_prompt(fmt: dict, fam: dict, family_selected: bool = True) -> str:
    gw, gh = _res(fmt, fam)
    tw, th = fmt["target"]
    neg_line = (
        "gerekli — bu aile negative prompt kullanır"
        if fam.get("supports_negative", True)
        else "KULLANILMAZ — negative_prompt alanını her zaman null döndür"
    )
    char_line = (
        "bu aile booru etiketleriyle eğitildi; bilinen anime/manga karakter adları doğrudan etiket olarak çalışır"
        if fam.get("character_mode") == "booru"
        else "bu ailede karakter ismi tanıma GÜVENİLMEZ; LoRA yoksa karakteri görsel özellikleriyle tarif et"
    )
    lines = [
        "GEÇERLİ SEÇİMLER (bu istek için):",
        f"- Format preset'i: {fmt['name']} — en-boy oranı {fmt['ratio']}, üretim çözünürlüğü {gw}x{gh}, nihai hedef {tw}x{th}",
        f"- Model ailesi: {fam['name']}",
        f"- Bu ailenin prompt stili rehberi: {fam['llm_guidance']}",
        f"- Negative prompt: {neg_line}",
        f"- Karakter istekleri: {char_line}",
    ]
    if not family_selected:
        lines.append(
            "- Kullanıcı model ailesi seçmedi; varsayılan olarak SDXL kullanılıyor. "
            "Üretim yaptığında note alanında bunu kısaca belirt."
        )
    return SYSTEM_PROMPT_BASE + "\n" + OUTPUT_PROTOCOL + "\n\n" + "\n".join(lines)


# ---------------------------------------------------------------------------
# LLM çıktısı ayrıştırma
# ---------------------------------------------------------------------------

_THINK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.S)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.S)


def _extract_json(text: str):
    """Metin içindeki ilk dengeli JSON objesini bulur (kod bloğu, düşünce
    etiketi veya öncesinde/sonrasında laf olsa bile)."""
    text = _THINK_RE.sub("", text)
    fence = _FENCE_RE.search(text)
    if fence:
        text = fence.group(1)
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start : i + 1])
                        except json.JSONDecodeError:
                            break
        start = text.find("{", start + 1)
    return None


def _clean_text(text: str) -> str:
    return _THINK_RE.sub("", text or "").strip()


def strip_thinking(text: str) -> str:
    """<think>…</think> akıl yürütme bloklarını atar. Sohbet geçmişine yazılan
    asistan yanıtlarında kullanılır: düşünce metni her turda modele geri
    gönderilirse küçük modellerin bağlam penceresini hızla doldurur."""
    return _clean_text(text)


def _norm_lora(raw):
    if not isinstance(raw, dict):
        return None
    name = str(raw.get("name") or raw.get("file") or "").strip()
    trigger = str(raw.get("trigger") or raw.get("trigger_word") or "").strip()
    if not name and not trigger:
        return None
    try:
        weight = float(raw.get("weight", 0.8))
    except (TypeError, ValueError):
        weight = 0.8
    weight = max(0.1, min(1.5, weight))
    return {"name": name or "(LoRA adı belirtilmedi)", "trigger": trigger or name, "weight": round(weight, 2)}


def parse_llm_output(raw: str) -> dict:
    """Model çıktısını normalize eder. JSON bozuksa sohbet mesajına düşer —
    konuşma asla kırılmaz."""
    data = _extract_json(raw or "")
    fallback = {
        "action": "chat",
        "message": _clean_text(raw)
        or "Yanıt üretemedim, isteğini bir kez daha yazar mısın?",
    }
    if not isinstance(data, dict):
        return fallback

    action = str(data.get("action", "")).strip().lower()
    if action == "generate":
        positive = str(data.get("positive_prompt") or data.get("positive") or "").strip()
        if not positive:
            msg = str(data.get("message") or data.get("note") or "").strip()
            return {"action": "chat", "message": msg or fallback["message"]}
        negative = data.get("negative_prompt", data.get("negative"))
        negative = str(negative).strip() if negative else None
        note = data.get("note")
        note = str(note).strip() if note else None
        return {
            "action": "generate",
            "positive": positive,
            "negative": negative or None,
            "lora": _norm_lora(data.get("lora")),
            "note": note,
        }
    if action == "chat":
        msg = str(data.get("message") or "").strip()
        return {"action": "chat", "message": msg or fallback["message"]}
    return fallback


# ---------------------------------------------------------------------------
# Paket kurulumu (deterministik guard'lar) ve Bölüm 6 şablonu
# ---------------------------------------------------------------------------

def _range_display(pair) -> str:
    a, b = pair
    return f"{a}-{b}" if a != b else f"{a}"


def _cfg_display(settings: dict) -> str:
    if settings.get("cfg_display"):
        return settings["cfg_display"]
    a, b = settings["cfg"]
    return f"{a}-{b}" if a != b else f"{float(a):g}"


def _final_label(gw: int, gh: int, tw: int, th: int) -> str:
    if (tw, th) == (gw, gh):
        return "ölçekleme gerekmez"
    return "downscale sonrası" if tw * th < gw * gh else "upscale sonrası"


def build_package(fmt: dict, fam: dict, parsed: dict) -> dict:
    """LLM'in yaratıcı çıktısını preset'lerden gelen teknik değerlerle birleştirir.
    Tüm kabul-kriteri garantileri burada uygulanır."""
    positive = parsed.get("positive", "").strip()
    negative = parsed.get("negative")

    # GUARD: aile negative desteklemiyorsa (Flux) her koşulda sil.
    if not fam.get("supports_negative", True):
        negative = None
    if negative is not None:
        negative = negative.strip() or None

    # GUARD: LoRA tetikleyici kelimesi positive prompt'ta yoksa başa eklenir —
    # LoRA trigger olmadan çoğu zaman hiç etki etmez, küçük modeller bunu unutabilir.
    lora = parsed.get("lora")
    trigger = (lora or {}).get("trigger", "").strip()
    if trigger and trigger.lower() not in positive.lower():
        positive = f"{trigger}, {positive}" if positive else trigger

    # GUARD: çözünürlük her zaman preset'ten (LLM'den asla alınmaz).
    gw, gh = _res(fmt, fam)
    tw, th = fmt["target"]
    s = fam["settings"]

    settings = {
        "gen": [gw, gh],
        "target": [tw, th],
        "final_label": _final_label(gw, gh, tw, th),
        "sampler": s["sampler"],
        "scheduler": s["scheduler"],
        "steps": _range_display(s["steps"]),
        "cfg": _cfg_display(s),
        "cfg_note": s.get("cfg_note"),
        "family_id": fam["id"],
        "family_label": fam["label"],
        "family_name": fam["name"],
        "format_id": fmt["id"],
        "format_name": fmt["name"],
        "ratio": fmt["ratio"],
        "format_note": fmt.get("note"),
        # ComfyUI'ye doğrudan gönderim için sayısal değerler:
        "steps_value": round(sum(s["steps"]) / 2),
        "cfg_value": round(sum(s["cfg"]) / 2, 1),
    }

    pkg = {
        "positive": positive,
        "negative": negative,
        "lora": lora,
        "note": parsed.get("note"),
        "settings": settings,
    }
    pkg["template_text"] = render_template(pkg)
    return pkg


def render_template(pkg: dict) -> str:
    """Bölüm 6'daki sabit şablon — tek üretim noktası burasıdır."""
    s = pkg["settings"]
    parts = ["POSITIVE PROMPT:", pkg["positive"]]
    if pkg.get("negative"):
        parts += ["", "NEGATIVE PROMPT:", pkg["negative"]]
    parts += [
        "",
        "ÖNERİLEN AYARLAR:",
        f"- Çözünürlük (üretim): {s['gen'][0]}x{s['gen'][1]}",
        f"- Nihai hedef ({s['final_label']}): {s['target'][0]}x{s['target'][1]}",
        f"- Sampler: {s['sampler']} ({s['scheduler']})",
        f"- Steps: {s['steps']}",
        f"- CFG Scale: {s['cfg']}",
        f"- Model ailesi: {s['family_label']}",
    ]
    lora = pkg.get("lora")
    if lora:
        parts.append(
            f"- LoRA (varsa): {lora['name']} + tetikleyici kelime: {lora['trigger']}"
            f" + önerilen ağırlık: {lora['weight']}"
        )
    return "\n".join(parts)
