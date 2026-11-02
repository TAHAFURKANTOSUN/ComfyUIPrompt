"""Uygulama yapılandırması: config.json + ortam değişkenleri + varsayılanlar."""
import copy
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DEFAULTS = {
    "llm": {
        # "ollama": Ollama'nın kendi /api/chat endpoint'i (yapılandırılmış JSON çıktı destekli, önerilen)
        # "openai": /v1/chat/completions (LM Studio, llama.cpp server vb. OpenAI-uyumlu sunucular için)
        "mode": "ollama",
        "base_url": "http://127.0.0.1:11434",
        "model": "qwen3:8b",
        # Görselden prompt tahmini için kullanılan çok-modlu (vision) model.
        # Alternatifler: qwen2.5vl:3b (daha az VRAM), gemma3:4b, llava:7b
        "vision_model": "qwen2.5vl:7b",
        "temperature": 0.7,
        # Ollama'nın modeli bellekte tutma süresi. Görsel üretimden önce VRAM'i boşaltmak
        # istiyorsanız kısa tutun (ör. "1m") ya da arayüzdeki "Belleği boşalt" düğmesini kullanın.
        "keep_alive": "5m",
        "timeout_s": 300,
    },
    "server": {
        "host": "127.0.0.1",
        "port": 8765,
        # Tarayıcıdan API'ye çapraz-köken (CORS) erişimine izin verilen kökenler.
        # Arayüz backend'in kendisinden sunulduğu (ve geliştirmede Vite proxy'si
        # kullanıldığı) için varsayılan olarak boştur: başka bir web sitesi bu yerel
        # API'yi kullanıp Ollama/ComfyUI'ye istek gönderemez.
        "cors_origins": [],
        # Host başlığı izin listesi (DNS rebinding koruması). Sunucu yalnızca
        # loopback'e bağlıyken uygulanır; LAN'dan erişim için host'u 0.0.0.0 yapıp
        # buraya makinenin adını/IP'sini ekleyin ya da ["*"] verin.
        "allowed_hosts": ["127.0.0.1", "localhost", "::1"],
    },
    "sessions": {
        # Sohbet geçmişi bu SQLite dosyasında kalıcı saklanır (proje köküne göre
        # göreli). ":memory:" verilirse sunucu kapanınca geçmiş silinir.
        "db_path": "data/sessions.db",
        # Bu sayının üzerindeki en eski oturumlar otomatik silinir.
        "max_sessions": 500,
    },
}


def load_config() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    path = ROOT / "config.json"
    if path.exists():
        try:
            user = json.loads(path.read_text(encoding="utf-8"))
            for key, val in user.items():
                if isinstance(val, dict) and isinstance(cfg.get(key), dict):
                    cfg[key].update(val)
                else:
                    cfg[key] = val
        except Exception as exc:  # bozuk config uygulamayı durdurmasın
            print(f"[config] config.json okunamadi, varsayilanlar kullaniliyor: {exc}")

    env_map = {
        "OLLAMA_BASE_URL": ("llm", "base_url"),
        "LLM_BASE_URL": ("llm", "base_url"),
        "LLM_MODEL": ("llm", "model"),
        "LLM_VISION_MODEL": ("llm", "vision_model"),
        "LLM_MODE": ("llm", "mode"),
        "HOST": ("server", "host"),
        "SESSIONS_DB": ("sessions", "db_path"),
        "PORT": ("server", "port"),
    }
    for env, (section, key) in env_map.items():
        raw = os.environ.get(env)
        if not raw:
            continue
        if key == "port":
            try:
                cfg[section][key] = int(raw)
            except ValueError:
                print(f"[config] Gecersiz {env}={raw!r}, yok sayiliyor.")
        else:
            cfg[section][key] = raw
    return cfg
