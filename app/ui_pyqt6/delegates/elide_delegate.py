from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QStyledItemDelegate


class ElideDelegate(QStyledItemDelegate):
    """A delegate that elides text in the middle if it's too long."""

    def initStyleOption(self, option, index) -> None:  # type: ignore[override]
        super().initStyleOption(option, index)
        option.textElideMode = Qt.TextElideMode.ElideMiddle
