from __future__ import annotations

from PyQt6.QtCore import QPoint, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .avatars import make_avatar_icon


class FriendsDock(QWidget):
    friendsChanged = pyqtSignal(list)  # emits full list
    avatarsChanged = pyqtSignal(dict)  # emits {nick: path}

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._all_friends: set[str] = set()
        self._online: set[str] = set()
        self._avatars: dict[str, str | None] = {}

        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)

        title = QLabel("Friends")
        v.addWidget(title)

        self.list = QListWidget(self)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._open_menu)
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

    def online_update(
        self, online_add: list[str] | None = None, online_remove: list[str] | None = None
    ) -> None:
        if online_add:
            self._online.update(online_add)
        if online_remove:
            self._online.difference_update(online_remove)
        self._refresh()

    def set_presence(self, online: set[str] | list[str]) -> None:
        self._online = set(online)
        self._refresh()

    def set_avatars(self, avatars: dict[str, str | None]) -> None:
        self._avatars = dict(avatars or {})
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
            item = QListWidgetItem(nick)
            item.setData(Qt.ItemDataRole.UserRole, nick)
            # avatar + presence dot
            path = self._avatars.get(nick)
            item.setIcon(make_avatar_icon(nick, path, 24, nick in self._online))
            self.list.addItem(item)

    def _open_menu(self, pos: QPoint) -> None:
        it = self.list.itemAt(pos)
        if not it:
            return
        nick = it.data(Qt.ItemDataRole.UserRole)
        m = QMenu(self)
        act_set = m.addAction("Set Avatar…")
        act_clear = m.addAction("Clear Avatar")
        act = m.exec(self.list.mapToGlobal(pos))
        if act == act_set:
            fn, _ = QFileDialog.getOpenFileName(
                self, "Choose Avatar", filter="Images (*.png *.jpg *.jpeg *.webp *.bmp)"
            )
            if fn:
                self._avatars[nick] = fn
                self._refresh()
                self.avatarsChanged.emit(dict(self._avatars))
        elif act == act_clear:
            if nick in self._avatars:
                self._avatars[nick] = None
                self._refresh()
                self.avatarsChanged.emit(dict(self._avatars))
