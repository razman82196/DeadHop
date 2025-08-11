from __future__ import annotations
import sys
import os
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from qasync import QEventLoop
import asyncio

APP_NAME = "Peach Client"

# Locate resources (icons)
_ICONS_DIR = Path(__file__).resolve().parent / "resources" / "icons"
_CUSTOM_ICONS_DIR = _ICONS_DIR / "custom"
_FALLBACK_ICON = _ICONS_DIR / "peach.svg"

def app_icon() -> QIcon:
    """Return the best available application icon.

    Prefers custom icons placed under `app/resources/icons/custom/`.
    """
    # Prefer a connect/plug icon for taskbar if available
    candidates = [
        # Connect-focused
        _CUSTOM_ICONS_DIR / "connected.svg",
        _CUSTOM_ICONS_DIR / "connected.png",
        _CUSTOM_ICONS_DIR / "connect.svg",
        _CUSTOM_ICONS_DIR / "connect.png",
        _CUSTOM_ICONS_DIR / "plug.svg",
        _CUSTOM_ICONS_DIR / "plug.png",
        # App-specific and peach fallbacks
        _CUSTOM_ICONS_DIR / "main app pixels.svg",
        _CUSTOM_ICONS_DIR / "main app pixels.png",
        _CUSTOM_ICONS_DIR / "peach.svg",
        _CUSTOM_ICONS_DIR / "peach.png",
        _FALLBACK_ICON,
    ]
    for p in candidates:
        try:
            if p.exists():
                return QIcon(str(p))
        except Exception:
            continue
    return QIcon()


def main() -> int:
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(app_icon())

    # Ensure Qt WebEngine is initialized after QApplication
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile  # type: ignore
        _ = QWebEngineProfile.defaultProfile()
    except Exception:
        pass

    # Theme via qt-material if present
    try:
        from qt_material import apply_stylesheet, list_themes
        themes = list_themes()
        # Prefer a dark theme if available
        preferred = "dark_teal.xml"
        theme = preferred if preferred in themes else (themes[0] if themes else None)
        if theme:
            apply_stylesheet(app, theme=theme)
    except Exception:
        pass

    # Import here to avoid circulars during PyQt detection
    # Support both package execution and PyInstaller one-file mode
    try:
        from .ui_pyqt6.main_window import MainWindow  # type: ignore
    except Exception:
        try:
            import sys as _sys
            from pathlib import Path as _Path
            root = _Path(__file__).resolve().parent.parent
            if str(root) not in _sys.path:
                _sys.path.append(str(root))
            from app.ui_pyqt6.main_window import MainWindow  # type: ignore
        except Exception:
            # Last resort: import from sibling folder if laid out flat
            try:
                from ui_pyqt6.main_window import MainWindow  # type: ignore
            except Exception as e:
                raise ImportError(f"Failed to import MainWindow: {e}")

    win = MainWindow()
    win.show()
    # qasync integration
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    with loop:
        return loop.run_forever()


if __name__ == "__main__":
    raise SystemExit(main())
