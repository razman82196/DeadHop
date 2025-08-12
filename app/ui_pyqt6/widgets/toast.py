from __future__ import annotations

from PyQt6.QtCore import QEasingCurve, QPropertyAnimation, QRect, Qt, QTimer
from PyQt6.QtWidgets import QLabel, QWidget


class Toast(QWidget):
    def __init__(self, text: str, parent: QWidget | None = None, duration_ms: int = 2200) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.label = QLabel(text, self)
        self.label.setStyleSheet(
            """
            QLabel {
                background-color: rgba(17, 21, 33, 220);
                color: #dde1ea;
                padding: 10px 14px;
                border-radius: 10px;
            }
            """
        )
        self.label.adjustSize()
        self.resize(self.label.size())

        self.anim = QPropertyAnimation(self, b"windowOpacity", self)
        self.anim.setDuration(180)
        self.anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(duration_ms)
        self._timer.timeout.connect(self._fade_out)

    def show_at_bottom(self) -> None:
        if not self.parent():
            self.show()
            return
        p = self.parent().geometry()
        w, h = self.width(), self.height()
        x = p.x() + (p.width() - w) // 2
        y = p.y() + p.height() - h - 24
        self.setGeometry(QRect(x, y, w, h))
        self.setWindowOpacity(0.0)
        self.show()
        self.anim.stop()
        self.anim.setStartValue(0.0)
        self.anim.setEndValue(1.0)
        self.anim.start()
        self._timer.start()

    def _fade_out(self) -> None:
        self.anim.stop()
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.close)
        self.anim.start()


class ToastHost:
    def __init__(self, parent: QWidget) -> None:
        self.parent = parent

    def show_toast(self, text: str, duration_ms: int = 2200) -> None:
        t = Toast(text, parent=self.parent, duration_ms=duration_ms)
        t.show_at_bottom()
