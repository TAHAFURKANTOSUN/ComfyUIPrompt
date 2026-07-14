async function req(path, options) {
  let resp;
  try {
    resp = await fetch(path, options);
  } catch {
    throw Object.assign(new Error("Sunucuya ulaşılamıyor. Backend çalışıyor mu?"), {
      code: "backend_down",
    });
  }
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const d = (data && data.detail) || data || {};
    throw Object.assign(new Error(d.message || "İstek başarısız oldu."), {
      code: d.code,
      hint: d.hint,
    });
  }
  return data;
}

const post = (path, body) =>
  req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

// Görseli tarayıcıda küçültüp JPEG data-URL'e çevirir (yerel vision modeline
// dev dosya göndermemek için; ~1024px analiz için fazlasıyla yeterli).
export function fileToResizedDataURL(file, maxDim = 1024, quality = 0.88) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Görsel okunamadı."));
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
        const w = Math.max(1, Math.round(img.width * scale));
        const h = Math.max(1, Math.round(img.height * scale));
        const canvas = document.createElement("canvas");
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff"; // saydam PNG'ler JPEG'e çevrilirken siyah olmasın
        ctx.fillRect(0, 0, w, h);
        ctx.drawImage(img, 0, 0, w, h);
        resolve(canvas.toDataURL("image/jpeg", quality));
      };
      img.onerror = () => reject(new Error("Bu dosya bir görsel olarak açılamadı."));
      img.src = reader.result;
    };
    reader.readAsDataURL(file);
  });
}

export const api = {
  config: () => req("/api/config"),
  status: (params = {}) => {
    const q = new URLSearchParams(
      Object.fromEntries(Object.entries(params).filter(([, v]) => v))
    ).toString();
    return req("/api/llm/status" + (q ? `?${q}` : ""));
  },
  chat: (body) => post("/api/chat", body),
  reset: (session_id) => post("/api/session/reset", { session_id }),
  unload: (body = {}) => post("/api/llm/unload", body),
  comfyCheckpoints: (url) => post("/api/comfyui/checkpoints", { url }),
  comfySend: (body) => post("/api/comfyui/send", body),
};
