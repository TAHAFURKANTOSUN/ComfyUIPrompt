import { useState } from "react";
import { Loader2, RefreshCw, X, Zap } from "lucide-react";
import { api } from "../api.js";
import useEscape from "../useEscape.js";

const inputCls =
  "w-full rounded-md border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-sm text-slate-100 " +
  "placeholder-slate-600 outline-none transition focus:border-indigo-500";

export default function SettingsModal({
  open,
  onClose,
  settings,
  setSettings,
  status,
  refreshStatus,
  defaults,
  setComfyLoras,
}) {
  const [ckpts, setCkpts] = useState([]);
  const [ckptBusy, setCkptBusy] = useState(false);
  const [ckptErr, setCkptErr] = useState(null);
  const [loraCount, setLoraCount] = useState(null);
  const [unloadMsg, setUnloadMsg] = useState(null);
  const [statusBusy, setStatusBusy] = useState(false);

  useEscape(open, onClose);

  if (!open) return null;

  const set = (key) => (e) => setSettings((s) => ({ ...s, [key]: e.target.value }));

  const doRefresh = async () => {
    setStatusBusy(true);
    await refreshStatus();
    setStatusBusy(false);
  };

  const fetchCkpts = async () => {
    setCkptBusy(true);
    setCkptErr(null);
    const url = settings.comfyUrl || "http://127.0.0.1:8188";
    if (!settings.comfyUrl) setSettings((s) => ({ ...s, comfyUrl: url }));
    try {
      const r = await api.comfyCheckpoints(url);
      const list = r.checkpoints || [];
      setCkpts(list);
      if (!list.length) setCkptErr("Sunucuda hiç checkpoint bulunamadı.");
      // Kayıtlı checkpoint bu sunucuda yoksa (silinmiş / farklı sunucu) ilkini seç;
      // aksi halde açılır liste bir şey gösterip başka bir değer gönderirdi.
      else if (!list.includes(settings.checkpoint))
        setSettings((s) => ({ ...s, checkpoint: list[0] }));
      // LoRA listesi opsiyonel: alınamazsa LoRA'sız gönderim yine çalışır.
      try {
        const lr = await api.comfyLoras(url);
        setComfyLoras(lr.loras || []);
        setLoraCount((lr.loras || []).length);
      } catch {
        setComfyLoras([]);
        setLoraCount(0);
      }
    } catch (e) {
      setCkptErr(e.message + (e.hint ? ` — ${e.hint}` : ""));
    }
    setCkptBusy(false);
  };

  const doUnload = async () => {
    setUnloadMsg("…");
    const body = {};
    if (settings.model) body.model = settings.model;
    if (settings.baseUrl) body.base_url = settings.baseUrl;
    if (settings.visionModel) body.vision_model = settings.visionModel;
    try {
      const r = await api.unload(body);
      setUnloadMsg(r.message);
    } catch (e) {
      setUnloadMsg(e.message);
    }
  };

  const models = status?.models || [];

  return (
    <div
      className="fixed inset-0 z-40 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className="max-h-[92vh] w-full max-w-lg overflow-y-auto rounded-t-2xl border border-slate-800 bg-slate-900 p-4 shadow-2xl sm:rounded-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 id="settings-title" className="text-sm font-semibold text-slate-100">Ayarlar</h2>
          <button
            onClick={onClose}
            aria-label="Kapat"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800"
          >
            <X size={16} />
          </button>
        </div>

        {/* LLM bölümü */}
        <section className="space-y-2.5 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-indigo-300">
              Yerel LLM (Ollama)
            </h3>
            <button
              onClick={doRefresh}
              className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-0.5 text-[11px] text-slate-300 hover:bg-slate-800"
            >
              {statusBusy ? (
                <Loader2 size={11} className="animate-spin" />
              ) : (
                <RefreshCw size={11} />
              )}
              Yenile
            </button>
          </div>

          <label className="block text-xs text-slate-400">
            Sunucu adresi
            <input
              className={inputCls + " mt-1"}
              placeholder={defaults?.base_url || "http://127.0.0.1:11434"}
              value={settings.baseUrl}
              onChange={set("baseUrl")}
            />
          </label>

          <label className="block text-xs text-slate-400">
            Model
            {models.length > 0 ? (
              <select
                className={inputCls + " mt-1"}
                value={settings.model || defaults?.model || ""}
                onChange={set("model")}
              >
                {!models.includes(settings.model || defaults?.model) && (
                  <option value={settings.model || defaults?.model}>
                    {(settings.model || defaults?.model) + " (yüklü değil)"}
                  </option>
                )}
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className={inputCls + " mt-1"}
                placeholder={defaults?.model || "qwen3:8b"}
                value={settings.model}
                onChange={set("model")}
              />
            )}
          </label>

          <label className="block text-xs text-slate-400">
            Görsel modeli (vision) — görselden prompt tahmini için
            {models.length > 0 ? (
              <select
                className={inputCls + " mt-1"}
                value={settings.visionModel || status?.vision_model || ""}
                onChange={set("visionModel")}
              >
                {!models.includes(settings.visionModel || status?.vision_model) && (
                  <option value={settings.visionModel || status?.vision_model}>
                    {(settings.visionModel || status?.vision_model) + " (yüklü değil)"}
                  </option>
                )}
                {models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            ) : (
              <input
                className={inputCls + " mt-1"}
                placeholder="qwen2.5vl:7b"
                value={settings.visionModel}
                onChange={set("visionModel")}
              />
            )}
          </label>

          <div className="space-y-0.5 text-[11px] leading-snug text-slate-500">
            {status?.ok ? (
              <>
                <p className="text-emerald-400">
                  Bağlı · {status.models.length} model yüklü
                  {!status.model_available && (
                    <span className="text-amber-400">
                      {" "}
                      — seçili sohbet modeli listede yok; <code>ollama pull</code> ile indirin.
                    </span>
                  )}
                </p>
                {!status.vision_available && (
                  <p className="text-amber-400">
                    Görsel modeli ({status.vision_model}) yüklü değil — görselden prompt için:{" "}
                    <code>ollama pull {status.vision_model}</code>
                  </p>
                )}
              </>
            ) : (
              <p className="text-rose-400">
                Ollama'ya ulaşılamıyor. Kurulum: ollama.com → <code>ollama pull qwen3:8b</code>
              </p>
            )}
          </div>

          <div className="flex items-center gap-2 border-t border-slate-800 pt-2">
            <button
              onClick={doUnload}
              title="LLM'i bellekten kaldırıp VRAM'i ComfyUI'ye bırakır"
              className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/40 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-300 hover:bg-amber-500/20"
            >
              <Zap size={13} />
              Belleği boşalt (VRAM)
            </button>
            {unloadMsg && <span className="text-[11px] text-slate-400">{unloadMsg}</span>}
          </div>
          <p className="text-[11px] leading-snug text-slate-500">
            İpucu: Görsel üretimine başlamadan önce LLM'i bellekten boşaltmak, ComfyUI ile VRAM
            çakışmasını önler.
          </p>
        </section>

        {/* ComfyUI bölümü */}
        <section className="mt-3 space-y-2.5 rounded-xl border border-slate-800 bg-slate-950/50 p-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-emerald-300">
            ComfyUI'ye doğrudan gönderme (opsiyonel)
          </h3>
          <label className="block text-xs text-slate-400">
            ComfyUI adresi
            <div className="mt-1 flex gap-2">
              <input
                className={inputCls}
                placeholder="http://127.0.0.1:8188"
                value={settings.comfyUrl}
                onChange={set("comfyUrl")}
              />
              <button
                onClick={fetchCkpts}
                disabled={ckptBusy}
                className="shrink-0 rounded-md border border-slate-700 px-2.5 text-xs text-slate-300 hover:bg-slate-800 disabled:opacity-50"
              >
                {ckptBusy ? <Loader2 size={13} className="animate-spin" /> : "Bağlan"}
              </button>
            </div>
          </label>
          {ckpts.length > 0 && (
            <label className="block text-xs text-slate-400">
              Checkpoint
              <select
                className={inputCls + " mt-1"}
                value={settings.checkpoint}
                onChange={set("checkpoint")}
              >
                {ckpts.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
          )}
          {ckptErr && <p className="text-[11px] text-rose-400">{ckptErr}</p>}
          {loraCount !== null && !ckptErr && (
            <p className="text-[11px] text-emerald-400">
              {loraCount > 0
                ? `${loraCount} LoRA bulundu — prompt kartlarından seçilebilir.`
                : "Sunucuda LoRA bulunamadı (LoRA'sız gönderim çalışır)."}
            </p>
          )}
          <p className="text-[11px] leading-snug text-slate-500">
            Basit text2img workflow'u kullanılır (checkpoint → [LoRA] → prompt → KSampler →
            kaydet). Kartta bir LoRA seçerseniz araya LoraLoader düğümü eklenir; asistanın
            önerdiği LoRA'ya en yakın dosya otomatik seçilir.
          </p>
        </section>

        <button
          onClick={onClose}
          className="mt-4 w-full rounded-lg bg-indigo-600 py-2 text-sm font-semibold text-white transition hover:bg-indigo-500"
        >
          Tamam
        </button>
      </div>
    </div>
  );
}
