import { useState } from "react";
import { Info, Loader2, Send, Star } from "lucide-react";
import CopyButton from "./CopyButton.jsx";
import { api } from "../api.js";

function Block({ title, text, mono = true }) {
  return (
    <div className="rounded-lg border border-slate-800 bg-slate-950/60">
      <div className="flex items-center justify-between border-b border-slate-800/80 px-3 py-1.5">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-indigo-300">
          {title}
        </span>
        <CopyButton text={text} />
      </div>
      <p
        className={
          "whitespace-pre-wrap px-3 py-2.5 text-[13px] leading-relaxed text-slate-200 " +
          (mono ? "font-mono" : "")
        }
      >
        {text}
      </p>
    </div>
  );
}

function SettingRow({ label, value }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="shrink-0 text-xs text-slate-400">{label}</span>
      <span className="text-right text-xs font-medium text-slate-100">{value}</span>
    </div>
  );
}

export default function PackageCard({ pkg, onFav, isFav, comfy, onOpenSettings }) {
  const s = pkg.settings;
  const [sendState, setSendState] = useState({ busy: false, msg: null, err: false });

  const settingsText = "ÖNERİLEN AYARLAR:" + pkg.template_text.split("ÖNERİLEN AYARLAR:")[1];

  const sendToComfy = async () => {
    setSendState({ busy: true, msg: null, err: false });
    try {
      const r = await api.comfySend({
        url: comfy.url,
        checkpoint: comfy.checkpoint,
        positive: pkg.positive,
        negative: pkg.negative || "",
        width: s.gen[0],
        height: s.gen[1],
        steps: s.steps_value,
        cfg: s.cfg_value,
        sampler: s.sampler,
        scheduler: s.scheduler,
      });
      setSendState({
        busy: false,
        msg: `ComfyUI kuyruğuna alındı (id: ${String(r.prompt_id).slice(0, 8)}…, seed: ${r.seed})`,
        err: false,
      });
    } catch (e) {
      setSendState({
        busy: false,
        msg: e.message + (e.hint ? ` — ${e.hint}` : ""),
        err: true,
      });
    }
  };

  return (
    <div className="w-full space-y-2.5 rounded-xl border border-slate-800 bg-slate-900/80 p-3 shadow-lg shadow-black/20">
      {/* Üst şerit: rozetler + favori */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[11px] font-semibold text-indigo-300">
          {s.family_label}
        </span>
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-300">
          {s.format_name}
        </span>
        <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[11px] text-slate-400">
          {s.ratio} · {s.gen[0]}x{s.gen[1]}
        </span>
        <button
          onClick={() => onFav(pkg)}
          title={isFav ? "Favorilerde" : "Favorilere ekle"}
          className={
            "ml-auto rounded-md p-1.5 transition " +
            (isFav
              ? "text-amber-400"
              : "text-slate-500 hover:bg-slate-800 hover:text-amber-300")
          }
        >
          <Star size={16} fill={isFav ? "currentColor" : "none"} />
        </button>
      </div>

      <Block title="Positive Prompt" text={pkg.positive} />
      {pkg.negative && <Block title="Negative Prompt" text={pkg.negative} />}

      {/* Ayarlar kartı */}
      <div className="rounded-lg border border-slate-800 bg-slate-950/60">
        <div className="flex items-center justify-between border-b border-slate-800/80 px-3 py-1.5">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">
            Önerilen Ayarlar
          </span>
          <CopyButton text={settingsText} />
        </div>
        <div className="grid grid-cols-1 gap-x-6 px-3 py-2 sm:grid-cols-2">
          <SettingRow label="Çözünürlük (üretim)" value={`${s.gen[0]}x${s.gen[1]}`} />
          <SettingRow label={`Nihai hedef (${s.final_label})`} value={`${s.target[0]}x${s.target[1]}`} />
          <SettingRow label="Sampler" value={`${s.sampler} (${s.scheduler})`} />
          <SettingRow label="Steps" value={s.steps} />
          <SettingRow label="CFG Scale" value={s.cfg} />
          <SettingRow label="Model ailesi" value={s.family_label} />
        </div>
        {(s.cfg_note || s.format_note) && (
          <div className="space-y-1 border-t border-slate-800/80 px-3 py-2">
            {s.cfg_note && <p className="text-[11px] leading-snug text-slate-400">{s.cfg_note}</p>}
            {s.format_note && (
              <p className="text-[11px] leading-snug text-slate-400">{s.format_note}</p>
            )}
          </div>
        )}
      </div>

      {/* LoRA satırı */}
      {pkg.lora && (
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
            LoRA
          </span>
          <span className="font-mono text-xs text-slate-200">{pkg.lora.name}</span>
          <span className="text-xs text-slate-400">
            tetikleyici: <span className="font-mono text-slate-200">{pkg.lora.trigger}</span> ·
            ağırlık: <span className="font-mono text-slate-200">{pkg.lora.weight}</span>
          </span>
          <CopyButton text={pkg.lora.trigger} label="Tetikleyiciyi kopyala" className="ml-auto" />
        </div>
      )}

      {/* Asistan notu */}
      {pkg.note && (
        <p className="flex items-start gap-1.5 px-1 text-xs italic leading-snug text-slate-400">
          <Info size={13} className="mt-0.5 shrink-0" />
          {pkg.note}
        </p>
      )}

      {/* Alt eylemler */}
      <div className="flex flex-wrap items-center gap-2 pt-0.5">
        <CopyButton text={pkg.template_text} label="Tümünü kopyala" />
        {comfy.enabled ? (
          <button
            onClick={sendToComfy}
            disabled={sendState.busy}
            className="inline-flex items-center gap-1.5 rounded-md border border-indigo-500/50 bg-indigo-500/10 px-2.5 py-1 text-xs font-medium text-indigo-300 transition hover:bg-indigo-500/20 disabled:opacity-50"
          >
            {sendState.busy ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Send size={13} />
            )}
            ComfyUI'ye Gönder
          </button>
        ) : (
          <button
            onClick={onOpenSettings}
            title="Ayarlardan ComfyUI adresi ve checkpoint seçin"
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-700 px-2.5 py-1 text-xs text-slate-500 transition hover:bg-slate-800 hover:text-slate-300"
          >
            <Send size={13} />
            ComfyUI'ye Gönder (ayar gerekli)
          </button>
        )}
      </div>
      {sendState.msg && (
        <p className={"px-1 text-xs " + (sendState.err ? "text-rose-400" : "text-emerald-400")}>
          {sendState.msg}
        </p>
      )}
    </div>
  );
}
