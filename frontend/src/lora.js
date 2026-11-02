// LLM'in önerdiği LoRA adını (ör. "miku_v2.safetensors" ya da yalnızca "mikuv2")
// ComfyUI sunucusundaki gerçek dosyalardan en yakınıyla eşleştirir.
// Eşleşme yoksa "" döner — kullanıcı listeden kendisi seçer.
const norm = (s) =>
  String(s || "")
    .toLowerCase()
    .split(/[\\/]/)
    .pop()
    .replace(/\.(safetensors|ckpt|pt|pth|bin)$/, "")
    .replace(/[^a-z0-9]/g, "");

export function matchLora(files, lora) {
  if (!lora || !files?.length) return "";
  const keys = [norm(lora.name), norm(lora.trigger)].filter((k) => k.length >= 3);
  for (const k of keys) {
    const f = files.find((x) => norm(x) === k);
    if (f) return f;
  }
  for (const k of keys) {
    const f = files.find((x) => {
      const n = norm(x);
      return n.length >= 3 && (n.includes(k) || k.includes(n));
    });
    if (f) return f;
  }
  return "";
}
