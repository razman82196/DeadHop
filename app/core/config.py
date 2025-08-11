from __future__ import annotations
import json
import os
from pathlib import Path

APP_NAME = "Peach Client"
DATA_DIR = Path(os.path.expanduser("~")) / ".peachbot_local"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_CFG = {
    "ui": {
        "theme": "dark",
        "accent": "#6C5CE7",
        "background": {"enabled": False, "path": "", "opacity": 0.22},
    },
    "servers": [
        # {"name": "Libera", "host": "irc.libera.chat", "port": 6697, "tls": True, "nick": "YourNick", "realname": "You", "channels": ["#test"]}
    ],
    "notifications": {"enabled": True},
    "logging": {"enabled": True, "dir": str(DATA_DIR / "logs")},
}


def ensure_config() -> dict:
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
