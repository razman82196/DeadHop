import json
from pathlib import Path

import pytest


def test_ensure_config_creates_file(monkeypatch, tmp_path):
    # Import lazily to patch module globals
    import app.main as app_main

    # Redirect DATA_DIR and CONFIG_PATH to a temp directory
    data_dir = tmp_path / ".peachbot_local"
    cfg_path = data_dir / "config.json"
    monkeypatch.setattr(app_main, "DATA_DIR", data_dir, raising=False)
    monkeypatch.setattr(app_main, "CONFIG_PATH", cfg_path, raising=False)

    # Run ensure_config and assert file is created with JSON
    cfg = app_main.ensure_config()
    assert cfg_path.exists(), "config.json should be created"

    # Load back and ensure it's valid JSON with expected top-level keys
    with cfg_path.open("r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert isinstance(loaded, dict)
    assert "ui" in loaded
    assert "notifications" in loaded

    # Change a value and persist via private helper
    loaded["ui"]["theme"] = "light"
    app_main._persist_cfg(loaded)  # noqa: SLF001 - test private helper intentionally
    with cfg_path.open("r", encoding="utf-8") as f:
        reloaded = json.load(f)
    assert reloaded["ui"]["theme"] == "light"
