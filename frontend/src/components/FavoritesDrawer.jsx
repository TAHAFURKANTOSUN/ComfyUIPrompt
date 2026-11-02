import { MessageSquarePlus, Star, Trash2, X } from "lucide-react";
import CopyButton from "./CopyButton.jsx";
import useEscape from "../useEscape.js";

export default function FavoritesDrawer({ open, onClose, favs, onUse, onDelete }) {
  useEscape(open, onClose);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Favori prompt'lar"
        className="flex h-full w-full max-w-md flex-col border-l border-slate-800 bg-slate-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <Star size={15} className="text-amber-400" />
            Favori prompt'lar
          </h2>
          <button
            onClick={onClose}
            aria-label="Kapat"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-2.5 overflow-y-auto p-3">
          {favs.length === 0 && (
            <p className="px-2 pt-6 text-center text-xs leading-relaxed text-slate-500">
              Henüz favori yok. Üretilen bir prompt kartındaki yıldız simgesine tıklayarak
              buraya kaydedebilirsiniz.
            </p>
          )}
          {favs.map((f) => (
            <div key={f.id} className="rounded-lg border border-slate-800 bg-slate-950/60 p-2.5">
              <div className="mb-1.5 flex items-center gap-1.5">
                <span className="rounded-full bg-indigo-500/15 px-2 py-0.5 text-[10px] font-semibold text-indigo-300">
                  {f.pkg.settings.family_label}
                </span>
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] text-slate-400">
                  {f.pkg.settings.format_name}
                </span>
                <span className="ml-auto text-[10px] text-slate-600">
                  {new Date(f.ts).toLocaleDateString("tr-TR")}
                </span>
              </div>
              <p className="mb-2 line-clamp-3 font-mono text-[11px] leading-snug text-slate-300">
                {f.pkg.positive}
              </p>
              <div className="flex items-center gap-2">
                <CopyButton text={f.pkg.template_text} label="Tümünü kopyala" />
                <button
                  onClick={() => onUse(f.pkg)}
                  className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-[11px] text-slate-300 hover:bg-slate-800"
                >
                  <MessageSquarePlus size={12} />
                  Sohbete ekle
                </button>
                <button
                  onClick={() => onDelete(f.id)}
                  title="Favoriden sil"
                  aria-label="Favoriden sil"
                  className="ml-auto rounded-md p-1 text-slate-500 hover:bg-slate-800 hover:text-rose-400"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
