// v1.1 — görselden prompt tahmini (vision) destekli
import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ImagePlus,
  Loader2,
  Palette,
  RotateCcw,
  Send,
  Settings,
  Sparkles,
  Star,
  X,
} from "lucide-react";
import { api, fileToResizedDataURL } from "./api.js";
import { iconFor } from "./icons.jsx";
import PackageCard from "./components/PackageCard.jsx";
import SettingsModal from "./components/SettingsModal.jsx";
import FavoritesDrawer from "./components/FavoritesDrawer.jsx";

const LS_SETTINGS = "cpa_settings_v1";
const LS_FAVS = "cpa_favs_v1";

const EXAMPLES = [
  "Sisli bir orman, gizemli atmosfer",
  "Yağmurlu gece şehir manzarası, neon ışıklar, sinematik",
  "Uzayda yalnız bir astronot, dev bir gezegenin önünde",
];

function loadLS(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

let msgSeq = 0;
const nextId = () => `m${Date.now()}_${msgSeq++}`;

export default function App() {
  const [cfg, setCfg] = useState(null);
  const [cfgErr, setCfgErr] = useState(null);
  const [formatId, setFormatId] = useState(null);
  const [familyId, setFamilyId] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [sessionId, setSessionId] = useState(null);
  const [status, setStatus] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [showFavs, setShowFavs] = useState(false);
  const [showStyles, setShowStyles] = useState(false);
  const [settings, setSettings] = useState(() => ({
    baseUrl: "",
    model: "",
    visionModel: "",
    comfyUrl: "",
    checkpoint: "",
    ...loadLS(LS_SETTINGS, {}),
  }));
  const [favs, setFavs] = useState(() => loadLS(LS_FAVS, []));
  const [image, setImage] = useState(null); // data URL — görselden prompt tahmini

  const chatRef = useRef(null);
  const inputRef = useRef(null);
  const fileRef = useRef(null);

  // --- yükleme ---
  useEffect(() => {
    api
      .config()
      .then((c) => {
        setCfg(c);
        setFormatId(c.defaults.format_id);
        setFamilyId(c.defaults.family_id);
      })
      .catch((e) => setCfgErr(e.message));
  }, []);

  const refreshStatus = useCallback(async () => {
    try {
      setStatus(
        await api.status({
          model: settings.model,
          base_url: settings.baseUrl,
          vision_model: settings.visionModel,
        })
      );
    } catch {
      setStatus(null);
    }
  }, [settings.model, settings.baseUrl, settings.visionModel]);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  // --- kalıcılık ---
  useEffect(() => {
    localStorage.setItem(LS_SETTINGS, JSON.stringify(settings));
  }, [settings]);
  useEffect(() => {
    localStorage.setItem(LS_FAVS, JSON.stringify(favs));
  }, [favs]);

  // --- otomatik kaydırma ---
  useEffect(() => {
    const el = chatRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs, busy]);

  const push = (msg) => setMsgs((m) => [...m, { id: nextId(), ...msg }]);

  const llmOverrides = () => {
    const o = {};
    if (settings.model) o.model = settings.model;
    if (settings.baseUrl) o.base_url = settings.baseUrl;
    if (settings.visionModel) o.vision_model = settings.visionModel;
    return Object.keys(o).length ? o : undefined;
  };

  // --- görsel ekleme ---
  const attachFile = async (file) => {
    if (!file || !file.type?.startsWith("image/")) return;
    try {
      setImage(await fileToResizedDataURL(file));
      inputRef.current?.focus();
    } catch (e) {
      push({ role: "assistant", kind: "error", text: e.message });
    }
  };

  // --- gönderme ---
  const send = async (textOverride) => {
    const text = (textOverride ?? input).trim();
    const img = textOverride ? null : image;
    if ((!text && !img) || busy || !formatId) return;
    setInput("");
    setImage(null);
    push({ role: "user", kind: "chat", text, image: img });
    setBusy(true);
    try {
      const r = await api.chat({
        session_id: sessionId,
        message: text,
        format_id: formatId,
        family_id: familyId,
        image: img || undefined,
        llm: llmOverrides(),
      });
      setSessionId(r.session_id);
      if (r.type === "package") {
        push({ role: "assistant", kind: "package", pkg: r.package });
      } else {
        push({ role: "assistant", kind: "chat", text: r.message });
      }
    } catch (e) {
      push({ role: "assistant", kind: "error", text: e.message, hint: e.hint });
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const newChat = async () => {
    if (sessionId) api.reset(sessionId).catch(() => {});
    setSessionId(null);
    setMsgs([]);
  };

  const changeFormat = (id) => {
    setFormatId(id);
    if (msgs.length && id !== formatId) {
      const f = cfg.formats.find((x) => x.id === id);
      push({ kind: "info", text: `Format değişti: ${f.name} (üretim çözünürlüğü otomatik güncellenecek)` });
    }
  };

  const changeFamily = (id) => {
    setFamilyId(id);
    if (msgs.length && id !== familyId) {
      const f = cfg.families.find((x) => x.id === id);
      push({ kind: "info", text: `Model ailesi değişti: ${f.name} (prompt stili buna göre üretilecek)` });
    }
  };

  // --- favoriler ---
  const isFav = (pkg) => favs.some((f) => f.pkg.template_text === pkg.template_text);
  const toggleFav = (pkg) => {
    setFavs((fs) =>
      fs.some((f) => f.pkg.template_text === pkg.template_text)
        ? fs.filter((f) => f.pkg.template_text !== pkg.template_text)
        : [{ id: nextId(), ts: Date.now(), pkg }, ...fs].slice(0, 100)
    );
  };
  const useFav = (pkg) => {
    setShowFavs(false);
    push({ role: "assistant", kind: "package", pkg });
  };

  const addStyle = (hint) => {
    setInput((i) => (i.trim() ? `${i.trim()} — stil: ${hint}` : `stil: ${hint}`));
    setShowStyles(false);
    inputRef.current?.focus();
  };

  // --- yükleme / hata ekranları ---
  if (cfgErr)
    return (
      <div className="flex h-full items-center justify-center p-6 text-center">
        <div className="max-w-sm rounded-xl border border-rose-500/40 bg-rose-500/5 p-5 text-sm text-rose-300">
          <AlertTriangle className="mx-auto mb-2" />
          Yapılandırma yüklenemedi: {cfgErr}
        </div>
      </div>
    );
  if (!cfg)
    return (
      <div className="flex h-full items-center justify-center text-slate-500">
        <Loader2 className="animate-spin" />
      </div>
    );

  const family = cfg.families.find((f) => f.id === familyId);
  const comfyReady = Boolean(settings.comfyUrl && settings.checkpoint);
  const statusOk = status?.ok;
  const modelShown = settings.model || cfg.llm.model;

  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col">
      {/* ---------- Üst bar ---------- */}
      <header className="flex items-center gap-2 px-3 pb-2 pt-3 sm:px-4">
        <Sparkles size={18} className="shrink-0 text-indigo-400" />
        <h1 className="truncate text-sm font-bold tracking-tight text-slate-100 sm:text-base">
          ComfyUI Prompt Asistanı
        </h1>
        <button
          onClick={() => setShowSettings(true)}
          title={statusOk ? `Bağlı: ${modelShown}` : "Ollama'ya ulaşılamıyor — ayarları açın"}
          className="ml-auto flex min-w-0 items-center gap-1.5 rounded-full border border-slate-800 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300 hover:border-slate-700"
        >
          <span
            className={
              "h-2 w-2 shrink-0 rounded-full " +
              (statusOk
                ? status.model_available
                  ? "bg-emerald-400"
                  : "bg-amber-400"
                : "bg-rose-500")
            }
          />
          <span className="hidden max-w-[140px] truncate sm:inline">
            {statusOk ? modelShown : "Ollama yok"}
          </span>
        </button>
        <button
          onClick={() => setShowFavs(true)}
          title="Favoriler"
          className="relative rounded-lg border border-slate-800 bg-slate-900 p-1.5 text-slate-300 hover:border-slate-700"
        >
          <Star size={15} />
          {favs.length > 0 && (
            <span className="absolute -right-1 -top-1 flex h-3.5 min-w-3.5 items-center justify-center rounded-full bg-amber-500 px-0.5 text-[9px] font-bold text-slate-950">
              {favs.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setShowSettings(true)}
          title="Ayarlar"
          className="rounded-lg border border-slate-800 bg-slate-900 p-1.5 text-slate-300 hover:border-slate-700"
        >
          <Settings size={15} />
        </button>
        <button
          onClick={newChat}
          title="Yeni sohbet"
          className="rounded-lg border border-slate-800 bg-slate-900 p-1.5 text-slate-300 hover:border-slate-700"
        >
          <RotateCcw size={15} />
        </button>
      </header>

      {/* ---------- Seçimler ---------- */}
      <section className="space-y-2 border-b border-slate-800/70 px-3 pb-2.5 sm:px-4">
        <div className="flex gap-1.5 overflow-x-auto pb-1 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          {cfg.formats.map((f) => {
            const Icon = iconFor(f.icon);
            const active = f.id === formatId;
            return (
              <button
                key={f.id}
                onClick={() => changeFormat(f.id)}
                title={`${f.name} — hedef ${f.target[0]}x${f.target[1]}`}
                className={
                  "flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition " +
                  (active
                    ? "border-indigo-500 bg-indigo-500/15 text-indigo-200"
                    : "border-slate-800 bg-slate-900 text-slate-400 hover:border-slate-700 hover:text-slate-200")
                }
              >
                <Icon size={14} />
                <span className="whitespace-nowrap">{f.name}</span>
                <span className={"whitespace-nowrap text-[10px] " + (active ? "text-indigo-300/80" : "text-slate-600")}>
                  {f.ratio}
                </span>
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-[11px] font-medium text-slate-500">Model ailesi:</label>
          <select
            value={familyId ?? ""}
            onChange={(e) => changeFamily(e.target.value)}
            className="rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-slate-100 outline-none transition focus:border-indigo-500"
          >
            {cfg.families.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
          {family && <span className="text-[11px] text-slate-500">{family.desc}</span>}
        </div>
      </section>

      {/* ---------- Sohbet ---------- */}
      <main ref={chatRef} className="flex-1 space-y-3 overflow-y-auto px-3 py-4 sm:px-4">
        {msgs.length === 0 && (
          <div className="mx-auto max-w-md rounded-2xl border border-slate-800 bg-slate-900/50 p-5 text-center">
            <Sparkles className="mx-auto mb-3 text-indigo-400" size={22} />
            <h2 className="mb-1.5 text-sm font-semibold text-slate-100">
              Fikrini anlat, ComfyUI prompt'una çevireyim
            </h2>
            <p className="mb-4 text-xs leading-relaxed text-slate-400">
              1. Yukarıdan format ve model ailesi seç · 2. Ne istediğini kendi
              cümlelerinle yaz · 3. Çıkan prompt'ları kopyala butonuyla ComfyUI
              node'larına yapıştır. Bir görsel de ekleyebilirsin{" "}
              <ImagePlus size={11} className="inline text-slate-500" /> — analiz
              edip benzerini üretecek prompt'u çıkarırım.
            </p>
            <div className="space-y-1.5">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  onClick={() => send(ex)}
                  className="block w-full rounded-lg border border-slate-800 bg-slate-950/60 px-3 py-1.5 text-left text-xs text-slate-300 transition hover:border-indigo-500/50 hover:text-indigo-200"
                >
                  “{ex}”
                </button>
              ))}
            </div>
          </div>
        )}

        {msgs.map((m) => {
          if (m.kind === "info")
            return (
              <div key={m.id} className="flex justify-center">
                <span className="rounded-full bg-slate-900 px-3 py-1 text-[10px] text-slate-500">
                  {m.text}
                </span>
              </div>
            );
          if (m.kind === "package")
            return (
              <div key={m.id} className="flex">
                <PackageCard
                  pkg={m.pkg}
                  onFav={toggleFav}
                  isFav={isFav(m.pkg)}
                  comfy={{ enabled: comfyReady, url: settings.comfyUrl, checkpoint: settings.checkpoint }}
                  onOpenSettings={() => setShowSettings(true)}
                />
              </div>
            );
          if (m.kind === "error")
            return (
              <div key={m.id} className="flex">
                <div className="max-w-[85%] rounded-xl rounded-tl-sm border border-rose-500/40 bg-rose-500/5 px-3 py-2 text-[13px] leading-relaxed text-rose-300">
                  <span className="mb-0.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide">
                    <AlertTriangle size={12} /> Hata
                  </span>
                  {m.text}
                  {m.hint && <p className="mt-1 text-xs text-rose-300/70">{m.hint}</p>}
                </div>
              </div>
            );
          const mine = m.role === "user";
          return (
            <div key={m.id} className={"flex " + (mine ? "justify-end" : "")}>
              <div
                className={
                  "max-w-[85%] whitespace-pre-wrap rounded-xl px-3 py-2 text-[13px] leading-relaxed " +
                  (mine
                    ? "rounded-tr-sm bg-indigo-600 text-white"
                    : "rounded-tl-sm border border-slate-800 bg-slate-900 text-slate-200")
                }
              >
                {m.image && (
                  <img
                    src={m.image}
                    alt="eklenen görsel"
                    className={"max-h-44 rounded-lg " + (m.text ? "mb-1.5" : "")}
                  />
                )}
                {m.text}
              </div>
            </div>
          );
        })}

        {busy && (
          <div className="flex">
            <div className="flex items-center gap-2 rounded-xl rounded-tl-sm border border-slate-800 bg-slate-900 px-3 py-2 text-[13px] text-slate-400">
              <Loader2 size={14} className="animate-spin text-indigo-400" />
              Prompt hazırlanıyor…
            </div>
          </div>
        )}
      </main>

      {/* ---------- Yazma alanı ---------- */}
      <footer
        className="border-t border-slate-800/70 px-3 pb-3 pt-2 sm:px-4"
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault();
          attachFile(e.dataTransfer?.files?.[0]);
        }}
      >
        {image && (
          <div className="mb-2 flex items-center gap-2">
            <div className="relative">
              <img
                src={image}
                alt="önizleme"
                className="h-16 rounded-lg border border-slate-700 object-cover"
              />
              <button
                onClick={() => setImage(null)}
                title="Görseli kaldır"
                className="absolute -right-2 -top-2 rounded-full border border-slate-600 bg-slate-800 p-0.5 text-slate-300 hover:bg-rose-600 hover:text-white"
              >
                <X size={12} />
              </button>
            </div>
            <span className="text-[11px] leading-snug text-slate-500">
              Görsel analiz edilip prompt'a çevrilecek.
              <br />
              İstersen yanına değişiklik notu yaz (ör. "ama gece olsun").
            </span>
          </div>
        )}
        {showStyles && cfg.styles.length > 0 && (
          <div className="mb-2 flex gap-1.5 overflow-x-auto pb-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {cfg.styles.map((st) => (
              <button
                key={st.id}
                onClick={() => addStyle(st.hint)}
                title={st.hint}
                className="shrink-0 rounded-full border border-slate-800 bg-slate-900 px-2.5 py-1 text-[11px] text-slate-300 transition hover:border-indigo-500/50 hover:text-indigo-200"
              >
                {st.name}
              </button>
            ))}
          </div>
        )}
        <div className="flex items-end gap-2">
          <button
            onClick={() => setShowStyles((v) => !v)}
            title="Stil kütüphanesi"
            className={
              "shrink-0 rounded-xl border p-2.5 transition " +
              (showStyles
                ? "border-indigo-500 bg-indigo-500/15 text-indigo-300"
                : "border-slate-800 bg-slate-900 text-slate-400 hover:border-slate-700")
            }
          >
            <Palette size={16} />
          </button>
          <button
            onClick={() => fileRef.current?.click()}
            title="Görsel ekle — görselden prompt tahmini"
            className={
              "shrink-0 rounded-xl border p-2.5 transition " +
              (image
                ? "border-indigo-500 bg-indigo-500/15 text-indigo-300"
                : "border-slate-800 bg-slate-900 text-slate-400 hover:border-slate-700")
            }
          >
            <ImagePlus size={16} />
          </button>
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              attachFile(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            onPaste={(e) => {
              const item = [...(e.clipboardData?.items || [])].find((i) =>
                i.type.startsWith("image/")
              );
              if (item) {
                e.preventDefault();
                attachFile(item.getAsFile());
              }
            }}
            rows={Math.min(4, Math.max(1, input.split("\n").length))}
            placeholder={
              image
                ? "İsteğe bağlı: görsel üzerinde değişiklik notu… (boş bırakılabilir)"
                : "Ne üretmek istediğini anlat… ya da bir görsel ekle/yapıştır"
            }
            className="max-h-32 flex-1 resize-none rounded-xl border border-slate-800 bg-slate-900 px-3 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none transition focus:border-indigo-500"
          />
          <button
            onClick={() => send()}
            disabled={busy || (!input.trim() && !image)}
            className="shrink-0 rounded-xl bg-indigo-600 p-2.5 text-white transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-40"
            title="Gönder (Enter)"
          >
            <Send size={16} />
          </button>
        </div>
        <p className="mt-1.5 hidden text-center text-[10px] text-slate-600 sm:block">
          Enter gönderir · Shift+Enter yeni satır · Görsel yapıştırılabilir/sürüklenebilir ·
          Prompt çıktıları İngilizce üretilir
        </p>
      </footer>

      <SettingsModal
        open={showSettings}
        onClose={() => setShowSettings(false)}
        settings={settings}
        setSettings={setSettings}
        status={status}
        refreshStatus={refreshStatus}
        defaults={cfg.llm}
      />
      <FavoritesDrawer
        open={showFavs}
        onClose={() => setShowFavs(false)}
        favs={favs}
        onUse={useFav}
        onDelete={(id) => setFavs((fs) => fs.filter((f) => f.id !== id))}
      />
    </div>
  );
}
