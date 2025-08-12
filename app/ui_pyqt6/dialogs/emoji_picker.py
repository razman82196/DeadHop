from __future__ import annotations

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

# Popular emojis with simple names for better search.
EMOJIS = [
    ("😀", "grinning"),
    ("😁", "beaming"),
    ("😂", "joy tears"),
    ("🤣", "rofl"),
    ("😊", "smile"),
    ("😉", "wink"),
    ("😍", "heart eyes"),
    ("😘", "kiss"),
    ("😜", "tongue wink"),
    ("🤔", "thinking"),
    ("🤗", "hug"),
    ("🤩", "star struck"),
    ("😎", "cool"),
    ("🥳", "party"),
    ("😇", "angel"),
    ("🙂", "slight smile"),
    ("🙃", "upside down"),
    ("😌", "relieved"),
    ("😴", "sleep"),
    ("😢", "cry"),
    ("😭", "sob"),
    ("😤", "steam nose"),
    ("😡", "angry"),
    ("🤬", "censored"),
    ("😱", "scream"),
    ("😳", "flushed"),
    ("🙄", "eyeroll"),
    ("😏", "smirk"),
    ("😬", "grimace"),
    ("👍", "thumbs up"),
    ("👎", "thumbs down"),
    ("👏", "clap"),
    ("🙌", "raised hands"),
    ("🙏", "pray"),
    ("💪", "flex"),
    ("🤝", "handshake"),
    ("🤞", "crossed fingers"),
    ("👌", "ok"),
    ("✌️", "victory"),
    ("🔥", "fire"),
    ("💯", "hundred"),
    ("✨", "sparkles"),
    ("🎉", "tada"),
    ("🥂", "cheers"),
    ("🍕", "pizza"),
    ("🍔", "burger"),
    ("🍟", "fries"),
    ("🍩", "donut"),
    ("☕", "coffee"),
    ("❤️", "red heart"),
    ("🧡", "orange heart"),
    ("💛", "yellow heart"),
    ("💚", "green heart"),
    ("💙", "blue heart"),
    ("💜", "purple heart"),
    ("🖤", "black heart"),
    ("🤍", "white heart"),
    ("🤎", "brown heart"),
    ("💔", "broken heart"),
    ("🤖", "robot"),
    ("💻", "laptop"),
    ("📱", "phone"),
    ("🎧", "headphones"),
    ("🎮", "game"),
]


class EmojiPickerDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Pick emoji")
        self.setWindowIcon(QIcon())
        self.setModal(True)
        self.setMinimumSize(520, 420)
        self.selected: str | None = None

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit(self)
        self.search.setPlaceholderText("Search…")
        top.addWidget(self.search)
        root.addLayout(top)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        holder = QWidget(scroll)
        grid = QGridLayout(holder)
        grid.setContentsMargins(6, 6, 6, 6)
        grid.setSpacing(6)

        self._buttons: list[QPushButton] = []
        cols = 12
        for idx, (em, name) in enumerate(EMOJIS):
            btn = QPushButton(em, holder)
            try:
                f = btn.font()
                f.setFamily("Segoe UI Emoji")
                f.setPointSize(max(f.pointSize() + 8, 20))
                btn.setFont(f)
            except Exception:
                pass
            btn.setFixedSize(48, 48)
            btn.setStyleSheet("QPushButton{padding:0; border:none; font-size:28px;}")
            btn.setToolTip(name)
            btn.setProperty("names", name)
            btn.clicked.connect(lambda _=False, e=em: self._choose(e))
            self._buttons.append(btn)
            r, c = divmod(idx, cols)
            grid.addWidget(btn, r, c)

        holder.setLayout(grid)
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self.search.textChanged.connect(self._apply_filter)

    def _choose(self, em: str) -> None:
        self.selected = em
        self.accept()

    def _apply_filter(self, text: str) -> None:
        t = (text or "").strip().lower()
        for b in self._buttons:
            names = (b.property("names") or "").lower()
            show = True if not t else (t in b.text().lower() or t in names)
            b.setVisible(show)


def pick_emoji(parent: QWidget | None = None) -> str | None:
    dlg = EmojiPickerDialog(parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.selected
    return None
