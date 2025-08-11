from __future__ import annotations
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QListWidget, QListWidgetItem, QLabel, QMenu
from PyQt6.QtCore import pyqtSignal, Qt


class MembersView(QWidget):
    memberAction = pyqtSignal(str, str)  # (nick, action)
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        self.title = QLabel("Members")
        lay.addWidget(self.title)

        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._open_menu)
        # Double-click to Query (open PM)
        self.list.itemDoubleClicked.connect(lambda it: self.memberAction.emit(it.text(), "Query"))
        lay.addWidget(self.list, 1)

        # start empty; names are provided by the IRC bridge via MainWindow._on_names

    def set_members(self, names: list[str]) -> None:
        """Replace the members list with the provided names."""
        self.list.clear()
        for name in names:
            QListWidgetItem(name, self.list)

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
