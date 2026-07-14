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
    "server": {"host": "127.0.0.1", "port": 8765},
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
        "LLM_MODE": ("llm", "mode"),
        "PORT": ("server", "port"),
    }
    for env, (section, key) in env_map.items():
        raw = os.environ.get(env)
        if raw:
            cfg[section][key] = int(raw) if key == "port" else raw
    return cfg
