"""presets/ altındaki config dosyalarını okur. Her istekte yeniden okunur —
dosyayı düzenleyince sunucuyu yeniden başlatmak gerekmez (dosyalar küçük)."""
import json
from pathlib import Path

PRESET_DIR = Path(__file__).resolve().parent.parent / "presets"


def _load(name: str) -> dict:
    return json.loads((PRESET_DIR / name).read_text(encoding="utf-8"))


def load_formats() -> dict:
    """id -> format preset sözlüğü."""
    return {f["id"]: f for f in _load("formats.json")["formats"]}


def default_format_id(formats: dict) -> str | None:
    """formats.json'daki 'default' alanı; silinmiş/yanlışsa ilk preset."""
    wanted = _load("formats.json").get("default")
    if wanted in formats:
        return wanted
    return next(iter(formats), None)


def load_families():
    """(id -> model ailesi sözlüğü, varsayılan aile id'si)"""
    raw = _load("model_families.json")
    return {f["id"]: f for f in raw["families"]}, raw.get("default", "sdxl")


def load_styles() -> list:
    try:
        return _load("styles.json")["styles"]
    except FileNotFoundError:
        return []
