import { useCallback, useEffect, useState } from "react";
import { History, Loader2, MessageSquare, Trash2, X } from "lucide-react";
import { api } from "../api.js";
import useEscape from "../useEscape.js";

function when(ts) {
  const d = new Date(ts * 1000);
  const today = new Date();
  return d.toDateString() === today.toDateString()
    ? d.toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" })
    : d.toLocaleDateString("tr-TR");
}

// Sunucuda (SQLite) kalıcı saklanan geçmiş sohbetler.
export default function HistoryDrawer({ open, onClose, onOpen, onDeleted, currentId, cfg }) {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);

  useEscape(open, onClose);

  const load = useCallback(async () => {
    setErr(null);
    try {
      setItems((await api.sessions()).sessions || []);
    } catch (e) {
      setErr(e.message);
      setItems([]);
    }
  }, []);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  if (!open) return null;

  const familyLabel = (id) => cfg?.families.find((f) => f.id === id)?.label || id;
  const formatName = (id) => cfg?.formats.find((f) => f.id === id)?.name || id;

  const remove = async (id) => {
    try {
      await api.deleteSession(id);
      setItems((xs) => xs.filter((x) => x.id !== id));
      onDeleted(id);
    } catch (e) {
      setErr(e.message);
    }
  };

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Geçmiş sohbetler"
        className="flex h-full w-full max-w-md flex-col border-l border-slate-800 bg-slate-900 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-slate-100">
            <History size={15} className="text-indigo-400" />
            Geçmiş sohbetler
          </h2>
          <button
            onClick={onClose}
            aria-label="Kapat"
            className="rounded-md p-1 text-slate-400 hover:bg-slate-800"
          >
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 space-y-2 overflow-y-auto p-3">
          {items === null && (
            <div className="flex justify-center pt-6 text-slate-500">
              <Loader2 className="animate-spin" size={18} />
            </div>
          )}
          {err && <p className="px-2 text-xs text-rose-400">{err}</p>}
          {items?.length === 0 && !err && (
            <p className="px-2 pt-6 text-center text-xs leading-relaxed text-slate-500">
              Henüz kayıtlı sohbet yok. Sohbetler bu bilgisayarda (data/sessions.db) saklanır
              ve sunucu yeniden başlasa da kaybolmaz.
            </p>
          )}
          {items?.map((s) => (
            <div
              key={s.id}
              className={
                "group flex items-start gap-2 rounded-lg border p-2.5 transition " +
                (s.id === currentId
                  ? "border-indigo-500/60 bg-indigo-500/10"
                  : "border-slate-800 bg-slate-950/60 hover:border-slate-700")
              }
            >
              <button
                onClick={() => onOpen(s.id)}
                className="flex min-w-0 flex-1 flex-col items-start gap-1 text-left"
              >
                <span className="flex w-full items-center gap-1.5">
                  <MessageSquare size={12} className="shrink-0 text-slate-500" />
                  <span className="truncate text-xs font-medium text-slate-200">{s.title}</span>
                </span>
                <span className="flex flex-wrap items-center gap-1.5 text-[10px] text-slate-500">
                  <span className="rounded-full bg-indigo-500/15 px-1.5 py-0.5 font-semibold text-indigo-300">
                    {familyLabel(s.family_id)}
                  </span>
                  <span className="truncate">{formatName(s.format_id)}</span>
                  <span>· {Math.ceil(s.message_count / 2)} tur</span>
                  <span>· {when(s.updated)}</span>
                </span>
              </button>
              <button
                onClick={() => remove(s.id)}
                title="Sohbeti sil"
                aria-label="Sohbeti sil"
                className="rounded-md p-1 text-slate-500 hover:bg-slate-800 hover:text-rose-400"
              >
                <Trash2 size={13} />
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
