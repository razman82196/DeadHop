from __future__ import annotations
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QPushButton, QLineEdit, QLabel
)

class FriendsDock(QWidget):
    friendsChanged = pyqtSignal(list)  # emits full list

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all_friends: set[str] = set()
        self._online: set[str] = set()

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        title = QLabel("Friends")
        v.addWidget(title)

        self.list = QListWidget(self)
        v.addWidget(self.list, 1)

        # Controls: add/remove
        h = QHBoxLayout()
        self.input = QLineEdit(self)
        self.input.setPlaceholderText("Add nick…")
        self.btn_add = QPushButton("Add", self)
        self.btn_del = QPushButton("Remove", self)
        h.addWidget(self.input, 1)
        h.addWidget(self.btn_add)
        h.addWidget(self.btn_del)
        v.addLayout(h)

        self.btn_add.clicked.connect(self._add)
        self.btn_del.clicked.connect(self._remove_selected)
        self.input.returnPressed.connect(self._add)

    def set_friends(self, friends: list[str]) -> None:
        self._all_friends = set(n.strip() for n in friends if n.strip())
        self._refresh()
        self.friendsChanged.emit(sorted(self._all_friends))

    def online_update(self, online_add: list[str] | None = None, online_remove: list[str] | None = None) -> None:
        if online_add:
            self._online.update(online_add)
        if online_remove:
            self._online.difference_update(online_remove)
        self._refresh()

    def _add(self) -> None:
        n = self.input.text().strip()
        if not n:
            return
        self.input.clear()
        if n not in self._all_friends:
            self._all_friends.add(n)
            self._refresh()
            self.friendsChanged.emit(sorted(self._all_friends))

    def _remove_selected(self) -> None:
        items = self.list.selectedItems()
        changed = False
        for it in items:
            nick = it.data(Qt.ItemDataRole.UserRole)
            if nick in self._all_friends:
                self._all_friends.remove(nick)
                if nick in self._online:
                    self._online.remove(nick)
                changed = True
        if changed:
            self._refresh()
            self.friendsChanged.emit(sorted(self._all_friends))

    def _refresh(self) -> None:
        self.list.clear()
        for nick in sorted(self._all_friends):
            prefix = "● " if nick in self._online else "○ "
            item = QListWidgetItem(f"{prefix}{nick}")
            item.setData(Qt.ItemDataRole.UserRole, nick)
            self.list.addItem(item)
