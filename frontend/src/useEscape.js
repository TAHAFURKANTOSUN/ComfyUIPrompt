import { useEffect } from "react";

// Açık bir modal/çekmeceyi Escape tuşuyla kapatır.
export default function useEscape(active, onClose) {
  useEffect(() => {
    if (!active) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, onClose]);
}
