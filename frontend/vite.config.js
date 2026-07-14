import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Geliştirme modunda /api istekleri backend'e (8765) yönlendirilir.
// Üretimde backend, frontend/dist'i kendisi sunar — proxy gerekmez.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8765" },
  },
});
