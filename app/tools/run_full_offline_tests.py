from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import List

# Safer WebEngine defaults for CI/headless must be set before QApplication
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu --no-sandbox --disable-software-rasterizer")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_OPENGL", "software")

from PyQt6.QtCore import QTimer, Qt, QCoreApplication
from PyQt6.QtWidgets import QApplication
from qasync import QEventLoop
from PyQt6.QtCore import QEventLoop as QtEventLoop
import asyncio

# Ensure project root is on sys.path so 'app' package resolves regardless of CWD
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set required Qt attributes BEFORE creating any QApplication (module scope)
try:
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_UseSoftwareOpenGL, True)
except Exception:
    pass

# Use absolute paths for fixtures to be independent of CWD
FIXTURE_REPLAY = ROOT / "app/tests/fixtures/sample_session.irc"
TINY_SCRIPT = ROOT / "app/tests/fixtures/tiny_scenario.script"


class IRCDPhase:
    def __init__(self, port: int = 6667) -> None:
        self.port = port
        self.ircd_proc: subprocess.Popen | None = None
        self.results: List[str] = []

    def log(self, msg: str) -> None:
        print(msg, flush=True)
        self.results.append(msg)

    def start_ircd(self) -> None:
        cmd = [sys.executable, "-m", "app.tools.tiny_ircd", "--port", str(self.port), "--script", str(TINY_SCRIPT)]
        self.ircd_proc = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parents[2]))
        self.log(f"[IRCD] Launched tiny_ircd on 127.0.0.1:{self.port}")
        time.sleep(0.6)

    def stop_ircd(self) -> None:
        if self.ircd_proc and self.ircd_proc.poll() is None:
            try:
                self.ircd_proc.terminate()
                try:
                    self.ircd_proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.ircd_proc.kill()
            except Exception:
                pass
            self.log("[IRCD] Stopped tiny_ircd")

    def run_client_checks(self) -> int:
        app = QApplication.instance() or QApplication(sys.argv)
        # qasync loop like main_pyqt6
        loop = QEventLoop(app)
        asyncio.set_event_loop(loop)
        # Initialize Qt WebEngine after QApplication is ready
        try:
            from PyQt6.QtWebEngineCore import QWebEngineProfile  # type: ignore
            _ = QWebEngineProfile.defaultProfile()
        except Exception:
            pass
        # Import MainWindow only after WebEngine is initialized
        from app.ui_pyqt6.main_window import MainWindow  # type: ignore
        win = MainWindow()
        win.show()
        status_buf: list[str] = []
        try:
            win.bridge.statusChanged.connect(lambda s: status_buf.append(s))
        except Exception:
            pass

        def connect_and_join() -> None:
            try:
                # Connect to local IRCD and join #test (no TLS)
                chans = ["#test"]
                # Use internal scheduler helper to invoke async slot
                if hasattr(win, "_schedule_async"):
                    win._schedule_async(win.bridge.connectHost, "127.0.0.1", self.port, False, "deadhop", "deadhop", "DeadHop", chans, None, None, False)
                    # Ensure join in case auto-join is not performed by manager
                    QTimer.singleShot(300, lambda: win._schedule_async(win.bridge.joinChannel, "127.0.0.1:#test"))
                else:
                    # Best-effort direct call (may not work without loop integration)
                    asyncio.ensure_future(win.bridge.connectHost("127.0.0.1", self.port, False, "deadhop", "deadhop", "DeadHop", chans, None, None, False))
                    asyncio.get_event_loop().call_later(0.3, lambda: asyncio.ensure_future(win.bridge.joinChannel("127.0.0.1:#test")))
                self.log("[IRCD] Connecting client and joining #test…")
            except Exception as e:
                self.log(f"[ERR] Connect scheduling failed: {e}")

        def checks() -> None:
            try:
                # Verify some UI state after scripted events
                self.log("[CHK] Performing UI checks…")
                # Helpers to get HTML and text from QWebEngineView
                html = ""
                text = ""
                try:
                    loop_local = QtEventLoop()
                    def _got_html(s: str) -> None:
                        nonlocal html
                        html = s or ""
                        loop_local.quit()
                    win.chat.page().toHtml(_got_html)
                    loop_local.exec()
                except Exception:
                    html = ""
                try:
                    loop_txt = QtEventLoop()
                    def _got_txt(s: str) -> None:
                        nonlocal text
                        text = s or ""
                        loop_txt.quit()
                    win.chat.page().runJavaScript("(function(){try{return document.body.innerText||'';}catch(e){return '';}})();", _got_txt)
                    loop_txt.exec()
                except Exception:
                    text = ""
                # Some lines may be filtered from chat; check status buffer as well
                def seen(s: str) -> bool:
                    if s in text:
                        return True
                    for ln in status_buf:
                        if s.lower() in ln.lower():
                            return True
                    return False
                checks = {
                    "MOTD": "offline scripted server",
                    "Topic": "Scripted channel",
                    "Names(alice)": "alice",
                    "Names(bob)": "bob",
                    "Hello": "hello from tiny ircd",
                    "Image": "image https://via.placeholder.com/200x100.png",
                    "YouTube": "video https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                }
                for label, needle in checks.items():
                    self.log(f"[OK] {label} seen" if seen(needle) else f"[WARN] {label} not seen")

                # HTML-level embed checks (inline iframe + img)
                try:
                    # Expect YouTube iframe embed
                    yid = "dQw4w9WgXcQ"
                    yt_iframe = f"https://www.youtube.com/embed/{yid}"
                    self.log("[OK] YouTube iframe embed present" if yt_iframe in html else "[WARN] YouTube iframe embed missing")
                    # Expect <img> tag for placeholder image URL
                    img_url = "https://via.placeholder.com/200x100.png"
                    self.log("[OK] Image <img> tag present" if img_url in html else "[WARN] Image <img> tag missing")
                    # Expect GIF url present (HTML or plain text fallback)
                    gif_url = "https://media.tenor.com/_Xx9k.gif"
                    has_gif = (gif_url in html) or (gif_url in text)
                    self.log("[OK] GIF URL present" if has_gif else "[WARN] GIF URL missing")
                except Exception:
                    self.log("[WARN] HTML embed checks failed")
                # Simulate clicking the media links to exercise handlers
                try:
                    from PyQt6.QtCore import QUrl as _QUrl
                    win._on_anchor_clicked(_QUrl("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
                    win._on_anchor_clicked(_QUrl("https://via.placeholder.com/200x100.png"))
                    win._on_anchor_clicked(_QUrl("https://example.org/"))
                except Exception:
                    pass

                # Video panel should be visible after simulated click
                try:
                    vis = win.video_panel.isVisible()
                    self.log("[OK] Video panel visible" if vis else "[WARN] Video panel not visible")
                except Exception:
                    self.log("[WARN] Video panel check failed")
                # BrowserWindow exists (from earlier image anchor routing)
                try:
                    bw = getattr(win, "browser_window", None)
                    self.log("[OK] BrowserWindow exists" if bw else "[WARN] BrowserWindow not created")
                except Exception:
                    self.log("[WARN] Browser window check failed")
            finally:
                QTimer.singleShot(300, loop.stop)

        with loop:
            QTimer.singleShot(50, connect_and_join)
            # Allow time for join + scripted events (<= 2.5s in script)
            QTimer.singleShot(3500, checks)
            loop.run_forever()
        return 0

    def run(self) -> int:
        try:
            self.start_ircd()
            return self.run_client_checks()
        finally:
            self.stop_ircd()


def run_replay_phase() -> int:
    cmd = [sys.executable, "-m", "app.tools.replay_irc_fixture", str(FIXTURE_REPLAY)]
    proc = subprocess.Popen(cmd, cwd=str(Path(__file__).resolve().parents[2]))
    return proc.wait()


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    os.chdir(root)
    # Phase A: tiny IRCD end-to-end
    ircd_phase = IRCDPhase(port=6667)
    code_a = ircd_phase.run()
    # Phase B: replay fixture into UI
    code_b = run_replay_phase()
    print(f"\nSummary: IRCD phase exit={code_a}, Replay phase exit={code_b}")
    return 0 if code_a == 0 and code_b == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
