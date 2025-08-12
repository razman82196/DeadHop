from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
    QWidget,
)

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
        # Use default delegate (avoid custom shadow painting to prevent double text)
        # Styling for flair
        self.setStyleSheet(
            """
            QWidget { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                       stop:0 #0f1116, stop:0.5 #121527, stop:1 #0f1220); }
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
            QLabel { font-weight: 700; color: #e6e6e6; padding: 6px 6px 2px 6px; text-shadow: 0 1px 2px rgba(0,0,0,.5); }
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
        self._me: str | None = None

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

    def set_self_nick(self, nick: str | None) -> None:
        try:
            self._me = (nick or "").strip()
        except Exception:
            self._me = None

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
        """Replace the members list with the provided names, grouped by status with separators."""
        self.list.clear()

        # Deduplicate case-insensitively, keeping the highest status prefix for each nick
        order = {"~": 0, "&": 1, "@": 2, "%": 3, "+": 4, "": 9}
        # key -> (status, nick_only, full_mask_or_none)
        best: dict[str, tuple[str, str, str | None]] = {}
        for raw in names or []:
            if not raw:
                continue
            status = ""
            name = raw
            if name and name[0] in ("~", "&", "@", "%", "+"):
                status = name[0]
                name = name[1:]
            base = name.strip()
            full_mask: str | None = None
            # If format like nick!user@host, keep tooltip with full mask but display only nick
            try:
                if "!" in base and "@" in base:
                    full_mask = base
                    base = base.split("!", 1)[0]
            except Exception:
                pass
            if not base:
                continue
            key = base.lower()
            prev = best.get(key)
            if not prev or order.get(status, 9) < order.get(prev[0], 9):
                best[key] = (status, base, full_mask)

        # Group by status
        groups: dict[str, list[str]] = {"~": [], "&": [], "@": [], "%": [], "+": [], "": []}
        for status, base, _mask in best.values():
            groups.setdefault(status, []).append(base)
        for k in list(groups.keys()):
            groups[k] = sorted(groups[k], key=lambda n: n.lower())

        headers = [
            ("~", "Owners"),
            ("&", "Admins"),
            ("@", "Operators"),
            ("%", "Half-ops"),
            ("+", "Voiced"),
            ("", "Members"),
        ]

        def add_header(text: str) -> None:
            it = QListWidgetItem(f"— {text} —")
            f = QFont()
            f.setBold(True)
            it.setFont(f)
            # Dim header color
            it.setForeground(QBrush(QColor("#bbbbbb")))
            # Make non-selectable
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsSelectable & ~Qt.ItemFlag.ItemIsEnabled)
            self.list.addItem(it)

        added_any = False
        me_low = (self._me or "").lower()
        for key, label in headers:
            names_in_group = groups.get(key) or []
            if not names_in_group:
                continue
            # Move my own nick to the top of its group
            try:
                for i, nm in enumerate(list(names_in_group)):
                    if nm.lower() == me_low:
                        names_in_group.insert(0, names_in_group.pop(i))
                        break
            except Exception:
                pass
            add_header(label)
            for base in names_in_group:
                status = key
                label_txt = f"{status} {base}" if status else base
                if base.lower() == me_low:
                    label_txt += "  (you)"
                it = QListWidgetItem(label_txt)
                # Set tooltip to full mask if available
                try:
                    mask = best.get(base.lower(), ("", base, None))[2]
                    if mask:
                        it.setToolTip(mask)
                except Exception:
                    pass
                f = QFont()
                if status in ("~", "&", "@"):
                    f.setBold(True)
                if base.lower() == me_low:
                    f.setItalic(True)
                it.setFont(f)
                col = self._nick_qcolor(base)
                it.setForeground(QBrush(col))
                path = self._avatars.get(base)
                it.setIcon(make_avatar_icon(base, path, 22, base in self._online, status))
                self.list.addItem(it)
                added_any = True

        self.title.setText("Members" if added_any else "Members (empty)")

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
