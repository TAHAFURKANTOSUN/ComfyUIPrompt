import { useState } from "react";
import { Check, Copy } from "lucide-react";

async function copyText(text) {
  if (navigator.clipboard && window.isSecureContext) {
    return navigator.clipboard.writeText(text);
  }
  // http üzerinden farklı bir makineden açılırsa yedek yöntem
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.opacity = "0";
  document.body.appendChild(ta);
  ta.select();
  const ok = document.execCommand("copy");
  document.body.removeChild(ta);
  if (!ok) throw new Error("copy failed");
}

export default function CopyButton({ text, label = "Kopyala", className = "" }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);

  const onClick = async () => {
    try {
      await copyText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Kopyalama başarısızsa kullanıcı "Kopyalandı" sanmasın.
      setFailed(true);
      setTimeout(() => setFailed(false), 2000);
    }
  };

  return (
    <button
      onClick={onClick}
      className={
        "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-medium transition " +
        (copied
          ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-300"
          : "border-slate-700 bg-slate-800/70 text-slate-300 hover:bg-slate-700 hover:text-white") +
        " " +
        className
      }
    >
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? "Kopyalandı" : failed ? "Kopyalanamadı — elle seçin" : label}
    </button>
  );
}
