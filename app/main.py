from __future__ import annotations

from pathlib import Path
import json
from typing import Any, Dict

# Paths are module-level so tests can monkeypatch them easily.
DATA_DIR: Path = Path.home() / ".peachbot_local"
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
