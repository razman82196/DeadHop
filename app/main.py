from __future__ import annotations

from pathlib import Path
import json
import os
import shutil
from typing import Any, Dict

# Paths are module-level so tests can monkeypatch them easily.
DATA_DIR: Path = Path.home() / ".deadhop_local"
CONFIG_PATH: Path = DATA_DIR / "config.json"


def _default_config() -> Dict[str, Any]:
    return {
        "ui": {
            "theme": "dark",
            "wrap": True,
            "timestamps": True,
        },
        "notifications": {
            "pm": True,
            "mentions": True,
            "highlights": [],
            "joins_parts": False,
        },
    }


def ensure_config() -> Dict[str, Any]:
    """Ensure the user config exists and return it as a dict.

    Tests may monkeypatch DATA_DIR and CONFIG_PATH before calling this.
    """
    _migrate_legacy_data_dir()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        cfg = _default_config()
        _persist_cfg(cfg)
        return cfg
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # If corrupted, replace with defaults
        cfg = _default_config()
        _persist_cfg(cfg)
        return cfg


def _persist_cfg(cfg: Dict[str, Any]) -> None:
    """Write the config dict to CONFIG_PATH (pretty JSON)."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def _migrate_legacy_data_dir() -> None:
    """One-time migrate ~/.peachbot_local to ~/.deadhop_local.
    If the old directory exists and the new one does not, attempt rename; otherwise copy.
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
        shutil.copytree(old_dir, new_dir)
    except Exception:
        pass


def main() -> None:
    """Launch the PyQt6 application entrypoint if available."""
    try:
        from .main_pyqt6 import main as ui_main  # type: ignore
    except Exception:
        # If UI is unavailable, just ensure config and exit gracefully
        ensure_config()
        return
    ui_main()


if __name__ == "__main__":
    main()
