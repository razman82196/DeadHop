from __future__ import annotations
import json
import os
import shutil
from pathlib import Path

APP_NAME = "DeadHop"
# New unified app data directory
DATA_DIR = Path(os.path.expanduser("~")) / ".deadhop_local"
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
    _migrate_legacy_data_dir()
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

def _migrate_legacy_data_dir() -> None:
    """One-time migrate ~/.peachbot_local to ~/.deadhop_local.
    - If old dir exists and new does not, attempt rename; fallback to copytree.
    - If new exists, leave old in place.
    Safe and idempotent.
    """
    home = Path(os.path.expanduser("~"))
    old_dir = home / ".peachbot_local"
    new_dir = DATA_DIR
    try:
        if not old_dir.exists() or new_dir.exists():
            return
        try:
            old_dir.rename(new_dir)
            return
        except Exception:
            pass
        # Fallback: copy recursively
        shutil.copytree(old_dir, new_dir)
    except Exception:
        # Best-effort only
        pass
