from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QLineEdit, QVBoxLayout


class TopicDialog(QDialog):
    def __init__(self, channel: str, current_topic: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit Topic — {channel}")
        v = QVBoxLayout(self)
        v.addWidget(QLabel(f"Channel: {channel}"))
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Enter new topic…")
        if current_topic:
            self.edit.setText(current_topic)
        v.addWidget(self.edit)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def value(self) -> str:
        return self.edit.text().strip()
