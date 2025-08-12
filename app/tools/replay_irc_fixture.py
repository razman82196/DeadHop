from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, List, Tuple
import os

# Set WebEngine-friendly environment before any Qt import
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox --disable-software-rasterizer")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_OPENGL", "software")

from PyQt6.QtCore import QTimer, Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication

# Ensure attributes are set before any QApplication
try:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
except Exception:
    pass


class ReplayDriver:
    """Replay a fixture of raw IRC lines to drive the UI without network.

    Minimal parser that understands a subset of numerics and common commands:
    - 001..005 welcome/info lines -> status
    - 332 topic
    - 353 NAMES aggregation
    - 366 end of NAMES (flush)
    - PRIVMSG/NOTICE/ACTION
    - JOIN/PART/MODE basic notices
    """

    def __init__(self, win: MainWindow, lines: List[str]) -> None:
        self.win = win
        self.lines = [ln.rstrip("\n") for ln in lines if ln.strip()]
        self._names: Dict[str, List[str]] = {}

    def _flush_names(self, ch: str) -> None:
        names = self._names.pop(ch, None)
        if names is not None:
            try:
                self.win._on_names(ch, names)
            except Exception:
                pass

    def _handle(self, raw: str) -> None:
        # Very light parsing, assumes modern server format
        try:
            msg = raw
            # Topic (332):  :server 332 nick #chan :topic text
            if " 332 " in msg:
                try:
                    parts = msg.split()
                    ch = parts[3]
                    topic = msg.split(" :", 1)[1]
                    self.win._chat_append(f"<i>Topic for {ch}:</i> {topic}")
                except Exception:
                    pass
                return
            # NAMES (353): :server 353 nick = #chan :nick1 nick2 @op +voice
            if " 353 " in msg:
                try:
                    ch = msg.split(" = ")[1].split()[0]
                    names = msg.split(" :", 1)[1].split()
                    # strip @ + symbols
                    names = [n.lstrip("@+") for n in names]
                    self._names.setdefault(ch, []).extend(names)
                except Exception:
                    pass
                return
            # End of NAMES (366)
            if " 366 " in msg:
                try:
                    ch = msg.split()[3]
                    self._flush_names(ch)
                except Exception:
                    pass
                return
            # PRIVMSG (ACTION if \x01ACTION)
            if " PRIVMSG " in msg:
                try:
                    prefix, rest = msg.split(" PRIVMSG ", 1)
                    ch, body = rest.split(" :", 1)
                    if body.startswith("\x01ACTION ") and body.endswith("\x01"):
                        body = f"* {prefix.split('!')[0][1:]} {body[8:-1]}"
                        # Render actions simply as italic line
                        self.win._chat_append(f"<i>{body}</i>")
                    else:
                        nick = prefix.split('!')[0][1:]
                        try:
                            html = self.win._format_message_html(nick, body)
                            self.win._chat_append(html)
                        except Exception:
                            self.win._chat_append(f"<b>{nick}:</b> {body}")
                except Exception:
                    pass
                return
            # NOTICE
            if " NOTICE " in msg:
                try:
                    _, rest = msg.split(" NOTICE ", 1)
                    target, body = rest.split(" :", 1)
                    self.win._chat_append(f"<i>-notice- [{target}] {body}</i>")
                except Exception:
                    pass
                return
            # JOIN/PART/MODE -> status line
            if " JOIN " in msg or " PART " in msg or " MODE " in msg:
                try:
                    self.win._on_status(msg)
                except Exception:
                    pass
                return
            # Generic status for anything else (001..005 etc.)
            if any(f" {n} " in msg for n in ("001","002","003","004","005","372","375","376")):
                try:
                    self.win._on_status(msg)
                except Exception:
                    pass
        except Exception:
            pass

    def run(self) -> None:
        self.win.show()
        delay = 40
        for i, ln in enumerate(self.lines):
            QTimer.singleShot(delay * (i + 1), lambda s=ln: self._handle(s))
        # finish after last
        QTimer.singleShot(delay * (len(self.lines) + 10), lambda: None)


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.tools.replay_irc_fixture <fixture_file>")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Fixture not found: {path}")
        return 2
    app = QApplication.instance() or QApplication(sys.argv)
    # Initialize WebEngine profile before importing MainWindow to avoid init errors
    try:
        from PyQt6.QtWebEngineCore import QWebEngineProfile  # type: ignore
        _ = QWebEngineProfile.defaultProfile()
    except Exception:
        pass
    # Import MainWindow only after WebEngine is initialized
    try:
        from app.ui_pyqt6.main_window import MainWindow  # type: ignore
    except Exception:
        from ui_pyqt6.main_window import MainWindow  # type: ignore
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception as e:
        print(f"Read error: {e}")
        return 2
    win = MainWindow()
    drv = ReplayDriver(win, lines)
    drv.run()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
