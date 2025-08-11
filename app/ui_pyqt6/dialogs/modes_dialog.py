from __future__ import annotations
from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QLabel, QDialogButtonBox

class ModesDialog(QDialog):
    def __init__(self, channel: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Channel Modes — {channel}")
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"Channel: {channel}"))
        v.addWidget(QLabel("Enter modes (e.g. +nt or +b nick!user@host):"))
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("+nt")
        v.addWidget(self.edit)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def value(self) -> str:
        return self.edit.text().strip()
