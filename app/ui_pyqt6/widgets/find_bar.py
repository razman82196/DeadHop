from __future__ import annotations
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel

class FindBar(QWidget):
    searchRequested = pyqtSignal(str, bool)  # (pattern, forward)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        h = QHBoxLayout(self)
        h.setContentsMargins(6,6,6,6)
        h.setSpacing(6)
        h.addWidget(QLabel("Find:"))
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Search in current buffer…")
        h.addWidget(self.edit, 1)
        self.btn_prev = QPushButton("Prev", self)
        self.btn_next = QPushButton("Next", self)
        h.addWidget(self.btn_prev)
        h.addWidget(self.btn_next)
        self.btn_prev.clicked.connect(lambda: self.searchRequested.emit(self.edit.text(), False))
        self.btn_next.clicked.connect(lambda: self.searchRequested.emit(self.edit.text(), True))
        self.edit.returnPressed.connect(lambda: self.searchRequested.emit(self.edit.text(), True))
