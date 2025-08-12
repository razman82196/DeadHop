from __future__ import annotations
import sys
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Import MainWindow and BridgeQt
from app.ui_pyqt6.main_window import MainWindow


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    w = MainWindow()
    w.show()

    # Simulated channels (composite labels as emitted by BridgeQt)
    ch1 = "libera:#peach"
    ch2 = "libera:#python"

    def step1():
        # Emit channels and set current channel
        try:
            w.bridge.channelsUpdated.emit([ch1, ch2])
            w.bridge.set_current_channel(ch1)
            # Emit names for both channels with different lists
            w.bridge.namesUpdated.emit(ch1, ["alice", "bob", "carol"])
            w.bridge.namesUpdated.emit(ch2, ["dave", "erin", "frank", "grace"])
        except Exception as e:
            print("Error step1:", e)

    def step2():
        # Verify members list corresponds to ch1 and tab-completion has 3 names
        try:
            names = [w.members.list.item(i).text() for i in range(w.members.list.count())]
            print("Members (", ch1, "):", names)
        except Exception as e:
            print("Error step2:", e)

    def step3():
        # Switch channel and verify members refresh to ch2
        try:
            w.bridge.set_current_channel(ch2)
            names = [w.members.list.item(i).text() for i in range(w.members.list.count())]
            print("Members (", ch2, "):", names)
        except Exception as e:
            print("Error step3:", e)

    def step4():
        # Test chat embed formatting for image and YouTube
        try:
            img_msg = w._format_message_html("tester", "Check this pic https://example.com/pic.jpg", ts=time.time())
            yt_msg = w._format_message_html("tester", "Watch https://www.youtube.com/watch?v=dQw4w9WgXcQ", ts=time.time())
            print("IMG HTML:", img_msg)
            print("YT  HTML:", yt_msg)
            w._chat_append(img_msg)
            w._chat_append(yt_msg)
        except Exception as e:
            print("Error step4:", e)

    def step5():
        # Open the built-in browser and navigate to a sample URL
        try:
            w._ensure_browser_dock()
            if w.browser_dock:
                w.browser_dock.show()
                w.browser_dock.url_edit.setText("https://www.wikipedia.org/")
                w.browser_dock._load_from_edit()
        except Exception as e:
            print("Error step5:", e)

    # Schedule steps
    QTimer.singleShot(200, step1)
    QTimer.singleShot(500, step2)
    QTimer.singleShot(900, step3)
    QTimer.singleShot(1300, step4)
    QTimer.singleShot(1700, step5)

    sys.exit(app.exec())


if __name__ == "__main__":
    run()
