from __future__ import annotations

import sys

from PyQt6.QtCore import QTimer, QUrl
from PyQt6.QtWidgets import QApplication

# Ensure app can import package
try:
    from app.ui_pyqt6.main_window import MainWindow  # type: ignore
except Exception:
    from ui_pyqt6.main_window import MainWindow  # type: ignore


class TestRunner:
    """Runs an extensive, offline UI/media test on MainWindow.

    This does not connect to IRC. It simulates channel list updates, names
    lists, message rendering (including images and YouTube), channel switching,
    tab-completion, members view updates, anchor-click routing, and the
    in-app BrowserWindow behavior.
    """

    def __init__(self, app: QApplication) -> None:
        self.app = app
        self.win = MainWindow()
        self.win.show()
        self.results: list[str] = []

    def log(self, msg: str) -> None:
        print(msg)
        self.results.append(msg)

    def simulate_channels(self) -> None:
        channels = ["net:#general", "net:#media", "net:#random"]
        try:
            # Sidebar population
            self.win.sidebar.set_channels(channels)
            self.win._channel_labels = list(channels)
            self.log("[OK] Channels populated in sidebar")
        except Exception as e:
            self.log(f"[ERR] Channels population failed: {e}")

    def simulate_names(self) -> None:
        data = {
            "net:#general": ["Alice", "Bob", "Carol", "dave"],
            "net:#media": ["MediaBot", "Alice", "Eve"],
            "net:#random": ["Zed", "Yan", "Xena"],
        }
        for ch, names in data.items():
            try:
                self.win._on_names(ch, names)
                self.log(f"[OK] Names updated for {ch}: {len(names)} nicks")
            except Exception as e:
                self.log(f"[ERR] _on_names for {ch} failed: {e}")

    def simulate_switch(self) -> None:
        try:
            self.win._on_current_channel_changed("net:#media")
            self.log("[OK] Switched to net:#media")
        except Exception as e:
            self.log(f"[ERR] Channel switch failed: {e}")

    def simulate_messages_and_links(self) -> None:
        # Plain text
        self.win._chat_append("<b>Welcome</b> to <i>DeadHop</i> test run")
        # Image embedding
        img_url = "https://via.placeholder.com/200x120.png?text=Test+Image"
        self.win._chat_append(f"Image: <a href='{img_url}'>{img_url}</a>")
        # YouTube
        yt = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.win._chat_append(f"YouTube: <a href='{yt}'>Link</a>")
        self.log("[OK] Messages with links appended")

        # Route image link to BrowserWindow
        try:
            self.win._on_anchor_clicked(QUrl(img_url))
            self.log("[OK] Image link routed to in-app browser")
        except Exception as e:
            self.log(f"[ERR] Image link routing failed: {e}")

        # Route YouTube to inline video panel
        try:
            self.win._on_anchor_clicked(QUrl(yt))
            visible = getattr(self.win.video_panel, "isVisible", lambda: False)()
            self.log(
                "[OK] YouTube routed to inline player"
                if visible
                else "[WARN] Video panel not visible after YouTube click"
            )
        except Exception as e:
            self.log(f"[ERR] YouTube routing failed: {e}")

    def simulate_tab_completion(self) -> None:
        try:
            # Set text on the internal QTextEdit of Composer
            self.win.composer.input.setPlainText("Al")
            # Place cursor at end
            cur = self.win.composer.input.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            self.win.composer.input.setTextCursor(cur)
            # Try completion
            handled = False
            if hasattr(self.win.composer, "_handle_tab"):
                self.win.composer._handle_tab(True)
                handled = True
            self.log(
                "[OK] Tab completion invoked"
                if handled
                else "[WARN] Tab completion method not available"
            )
        except Exception as e:
            self.log(f"[ERR] Tab completion failed: {e}")

    def simulate_reverse_tab_completion(self) -> None:
        try:
            # Continue cycling in reverse
            handled = False
            if hasattr(self.win.composer, "_handle_tab"):
                self.win.composer._handle_tab(False)
                handled = True
            self.log(
                "[OK] Reverse tab completion invoked"
                if handled
                else "[WARN] Reverse completion not available"
            )
        except Exception as e:
            self.log(f"[ERR] Reverse tab completion failed: {e}")

    def simulate_member_actions(self) -> None:
        # Exercise _on_member_action fallbacks; bridge may not implement raw cmds
        try:
            for action in ("whois", "query", "kick", "ban", "op", "deop", "add friend"):
                self.win._on_member_action("Alice", action)
            self.log("[OK] Member actions invoked (whois/query/kick/ban/op/deop/add friend)")
        except Exception as e:
            self.log(f"[ERR] Member actions failed: {e}")

    def simulate_find(self) -> None:
        try:
            self.win._on_find("YouTube", True)
            self.win._on_find("Welcome", False)
            self.log("[OK] Find in buffer invoked (forward/backward)")
        except Exception as e:
            self.log(f"[ERR] Find failed: {e}")

    def simulate_video_pop(self) -> None:
        try:
            # Pop current video into browser window
            if hasattr(self.win, "video_panel"):
                self.win.video_panel._do_pop()
            self.log("[OK] Video pop-out invoked")
        except Exception as e:
            self.log(f"[ERR] Video pop-out failed: {e}")

    def simulate_browser_toggle_and_reset(self) -> None:
        try:
            self.win._toggle_browser_panel()
            self.win._reset_browser_profile()
            # After reset, open a site again to reinit
            self.win._open_internal_browser("https://example.org")
            self.log("[OK] Browser toggled, profile reset, and reopened")
        except Exception as e:
            self.log(f"[ERR] Browser toggle/reset failed: {e}")

    def simulate_pm_query_switch(self) -> None:
        try:
            # Ensure PM created via member action then switch back
            self.win._on_member_action("Bob", "query")
            self.win._on_current_channel_changed("net:#general")
            self.log("[OK] PM created and channel switched back to #general")
        except Exception as e:
            self.log(f"[ERR] PM/query switch failed: {e}")

    def verify_browser_window(self) -> None:
        try:
            bw = getattr(self.win, "browser_window", None)
            if bw is None:
                # open a url to ensure creation
                self.win._on_anchor_clicked(QUrl("https://example.com"))
                bw = getattr(self.win, "browser_window", None)
            if bw is not None:
                self.log("[OK] BrowserWindow exists")
            else:
                self.log("[ERR] BrowserWindow was not created")
        except Exception as e:
            self.log(f"[ERR] BrowserWindow verification failed: {e}")

    def run(self) -> None:
        # Schedule steps sequentially in the Qt event loop
        steps = [
            self.simulate_channels,
            self.simulate_names,
            self.simulate_switch,
            self.simulate_messages_and_links,
            self.simulate_tab_completion,
            self.simulate_reverse_tab_completion,
            self.simulate_member_actions,
            self.simulate_find,
            self.simulate_video_pop,
            self.simulate_browser_toggle_and_reset,
            self.simulate_pm_query_switch,
            self.verify_browser_window,
            self.finish,
        ]
        delay = 300
        for i, step in enumerate(steps):
            QTimer.singleShot(delay * (i + 1), step)

    def finish(self) -> None:
        self.log("[DONE] Extensive UI/media test complete. Exiting…")
        QTimer.singleShot(300, self.app.quit)


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    runner = TestRunner(app)
    runner.run()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
