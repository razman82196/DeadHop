from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import QLabel, QListWidget, QListWidgetItem, QMenu, QVBoxLayout, QWidget

from .avatars import make_avatar_icon


class MembersView(QWidget):
    memberAction = pyqtSignal(str, str)  # (nick, action)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.title = QLabel("Members")
        lay.addWidget(self.title)
        self.list = QListWidget(self)
        # Styling for flair
        self.setStyleSheet(
            """
            QWidget {
                background: #0f1116;
            }
            QListWidget {
                border: none;
                padding: 6px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: rgba(130, 177, 255, 0.18);
            }
            QLabel { font-weight: 700; color: #e6e6e6; padding: 6px 6px 2px 6px; }
            """
        )
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._open_menu)
        # Double-click to Query (open PM)
        self.list.itemDoubleClicked.connect(lambda it: self.memberAction.emit(it.text(), "Query"))
        lay.addWidget(self.list, 1)

        # start empty; names are provided by the IRC bridge via MainWindow._on_names
        self._online: set[str] = set()
        self._avatars: dict[str, str | None] = {}

    def set_presence(self, online: set[str] | list[str]) -> None:
        try:
            self._online = set(online)
            # Refresh icons only
            for i in range(self.list.count()):
                it = self.list.item(i)
                raw = it.text()
                status = ""
                name = raw
                if name and name[0] in ("~", "&", "@", "%", "+"):
                    status = name[0]
                    name = name[1:].strip()
                path = self._avatars.get(name)
                it.setIcon(make_avatar_icon(name, path, 22, name in self._online, status))
        except Exception:
            pass

    def set_avatars(self, avatars: dict[str, str | None]) -> None:
        try:
            self._avatars = dict(avatars or {})
            # Refresh icons only
            for i in range(self.list.count()):
                it = self.list.item(i)
                raw = it.text()
                status = ""
                name = raw
                if name and name[0] in ("~", "&", "@", "%", "+"):
                    status = name[0]
                    name = name[1:].strip()
                path = self._avatars.get(name)
                it.setIcon(make_avatar_icon(name, path, 22, name in self._online, status))
        except Exception:
            pass

    def set_members(self, names: list[str]) -> None:
        """Replace the members list with the provided names."""
        self.list.clear()

        # Sort by IRC status prefix
        def weight(n: str) -> int:
            if not n:
                return 99
            c = n[0]
            order = {"~": 0, "&": 1, "@": 2, "%": 3, "+": 4}
            return order.get(c, 9)

        for raw in sorted(names or [], key=lambda x: (weight(x), x.lower())):
            name = raw
            # status prefix
            status = ""
            if name and name[0] in ("~", "&", "@", "%", "+"):
                status = name[0]
                name = name[1:]
            it = QListWidgetItem(f"{status} {name}" if status else name)
            # Font weight for status
            f = QFont()
            if status in ("~", "&", "@"):
                f.setBold(True)
            it.setFont(f)
            # Deterministic color per nick
            col = self._nick_qcolor(name)
            it.setForeground(QBrush(col))
            # Avatar icon with presence overlay
            path = self._avatars.get(name)
            it.setIcon(make_avatar_icon(name, path, 22, name in self._online, status))
            # Subtle background hover handled by stylesheet
            self.list.addItem(it)
        self.title.setText("Members")

    def _nick_qcolor(self, nick: str) -> QColor:
        try:
            s = (nick or "").lower().encode("utf-8")
            h = 0
            for b in s:
                h = (h * 131 + int(b)) & 0xFFFFFFFF
            hue = h % 360
            # Convert HSL to RGB for QColor
            # Use medium saturation/lightness for readability
            import colorsys

            r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.60, 0.65)
            return QColor(int(r * 255), int(g * 255), int(b * 255))
        except Exception:
            return QColor("#82b1ff")

    def _open_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if not item:
            return
        nick = item.text()
        m = QMenu(self)
        for label in ["WHOIS", "Query", "Add Friend", "Kick", "Ban", "Op", "Deop"]:
            act = m.addAction(label)
            act.triggered.connect(lambda _=False, a=label, n=nick: self.memberAction.emit(n, a))
        m.exec(self.list.mapToGlobal(pos))

    def selected_nick(self) -> str | None:
        it = self.list.currentItem()
        return it.text() if it else None
