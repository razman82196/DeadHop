import json
import os
import shutil
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~")) / ".deadhop_local"
CONFIG_PATH = DATA_DIR / "config.json"

DEFAULT_CFG = {
    "ui": {"theme": "dark", "accent": "#7c5cff"},
    "servers": [],
    "deadhop": {"enabled": True, "api_base": "http://127.0.0.1:11434", "model": "llama3:8b"},
    "notifications": {
        "enabled": True,
        "events": {"mention": True, "pm": True, "connect": True, "error": True},
        "sound": {"path": "", "volume": 0.8},  # path to WAV file; if empty, no sound
    },
    "logging": {"enabled": True, "dir": str(DATA_DIR / "logs")},
}


def load_config() -> dict:
    _migrate_legacy_data_dir()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    cfg: dict
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception:
            cfg = DEFAULT_CFG.copy()
    else:
        cfg = DEFAULT_CFG.copy()
        _persist_cfg(cfg)
    # Migrate legacy 'peach' namespace to 'deadhop' if present
    try:
        if "deadhop" not in cfg and "peach" in cfg and isinstance(cfg["peach"], dict):
            cfg["deadhop"] = cfg.get("peach", {})
            _persist_cfg(cfg)
    except Exception:
        pass
    return cfg


def _migrate_legacy_data_dir() -> None:
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
        shutil.copytree(old_dir, new_dir)
    except Exception:
        pass


def _persist_cfg(cfg: dict) -> None:
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
