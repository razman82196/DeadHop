import json
import os
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~")) / ".peachbot_local"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_CFG = {
    "ui": {"theme": "dark", "accent": "#7c5cff"},
    "servers": [],
    "peach": {"enabled": True, "api_base": "http://127.0.0.1:11434", "model": "peach-gemma-merged"},
    "notifications": {
        "enabled": True,
        "events": {"mention": True, "pm": True, "connect": True, "error": True},
        "sound": {"path": "", "volume": 0.8},  # path to WAV file; if empty, no sound
    },
    "logging": {"enabled": True, "dir": str(DATA_DIR / "logs")},
}


def load_config() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(DEFAULT_CFG, f, ensure_ascii=False, indent=2)
    return DEFAULT_CFG
