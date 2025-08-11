from __future__ import annotations
from typing import Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSlider, QCheckBox, QDialogButtonBox, QFontDialog
)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    def __init__(self,
                 parent=None,
                 theme_options: list[str] | None = None,
                 current_theme: Optional[str] = None,
                 opacity: float = 1.0,
                 font_family: Optional[str] = None,
                 font_point_size: Optional[int] = None,
                 highlight_words: list[str] | None = None,
                 friends: list[str] | None = None,
                 word_wrap: bool = True,
                 show_timestamps: bool = False,
                 autoconnect: bool = False,
                 auto_negotiate: bool = True,
                 prefer_tls: bool = True,
                 try_starttls: bool = False,
                 ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(10)

        # Theme
        h_theme = QHBoxLayout()
        h_theme.addWidget(QLabel("Theme:"))
        self.cmb_theme = QComboBox(self)
        theme_options = theme_options or []
        self.cmb_theme.addItems(theme_options)
        if current_theme and current_theme in theme_options:
            self.cmb_theme.setCurrentText(current_theme)
        h_theme.addWidget(self.cmb_theme, 1)
        v.addLayout(h_theme)

        # Opacity
        h_op = QHBoxLayout()
        h_op.addWidget(QLabel("Window Opacity:"))
        self.sld_opacity = QSlider(Qt.Orientation.Horizontal, self)
        self.sld_opacity.setRange(50, 100)
        self.sld_opacity.setValue(int(opacity * 100))
        h_op.addWidget(self.sld_opacity, 1)
        v.addLayout(h_op)

        # Font
        h_font = QHBoxLayout()
        h_font.addWidget(QLabel("Font:"))
        self.le_font = QLineEdit(self)
        if font_family:
            if font_point_size:
                self.le_font.setText(f"{font_family}, {font_point_size}pt")
            else:
                self.le_font.setText(font_family)
        self.btn_font = QPushButton("Choose…", self)
        h_font.addWidget(self.le_font, 1)
        h_font.addWidget(self.btn_font)
        v.addLayout(h_font)

        # Word wrap and timestamps
        self.chk_wrap = QCheckBox("Word Wrap in Chat", self)
        self.chk_wrap.setChecked(word_wrap)
        v.addWidget(self.chk_wrap)
        self.chk_ts = QCheckBox("Show Timestamps", self)
        self.chk_ts.setChecked(show_timestamps)
        v.addWidget(self.chk_ts)

        # Highlight words
        h_hl = QHBoxLayout()
        h_hl.addWidget(QLabel("Highlight Words (comma-separated):"))
        self.le_highlight = QLineEdit(self)
        self.le_highlight.setText(", ".join(highlight_words or []))
        h_hl.addWidget(self.le_highlight, 1)
        v.addLayout(h_hl)

        # Friends
        h_fr = QHBoxLayout()
        h_fr.addWidget(QLabel("Friends (comma-separated):"))
        self.le_friends = QLineEdit(self)
        self.le_friends.setText(", ".join(friends or []))
        h_fr.addWidget(self.le_friends, 1)
        v.addLayout(h_fr)

        # Auto-connect toggle
        self.chk_autoc = QCheckBox("Auto-connect on startup", self)
        self.chk_autoc.setChecked(bool(autoconnect))
        v.addWidget(self.chk_autoc)

        # Auto-negotiate IRCv3 features
        self.chk_auto_neg = QCheckBox("Auto-negotiate IRCv3 features", self)
        self.chk_auto_neg.setChecked(bool(auto_negotiate))
        v.addWidget(self.chk_auto_neg)

        # Prefer TLS/STARTTLS
        self.chk_prefer_tls = QCheckBox("Prefer TLS/STARTTLS", self)
        self.chk_prefer_tls.setChecked(bool(prefer_tls))
        v.addWidget(self.chk_prefer_tls)

        # Try STARTTLS when available (requires server support)
        self.chk_try_starttls = QCheckBox("Try STARTTLS when available", self)
        self.chk_try_starttls.setChecked(bool(try_starttls))
        v.addWidget(self.chk_try_starttls)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self)
        v.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self.btn_font.clicked.connect(self._choose_font)

        self._font_family = font_family
        self._font_pt = font_point_size or 0

    def _choose_font(self) -> None:
        font, ok = QFontDialog.getFont(parent=self)
        if ok:
            self._font_family = font.family()
            self._font_pt = font.pointSize()
            self.le_font.setText(f"{self._font_family}, {self._font_pt}pt")

    # Accessors
    def selected_theme(self) -> Optional[str]:
        return self.cmb_theme.currentText() or None

    def selected_opacity(self) -> float:
        return float(self.sld_opacity.value()) / 100.0

    def selected_font(self) -> tuple[Optional[str], Optional[int]]:
        return self._font_family, (self._font_pt or None)

    def selected_highlight_words(self) -> list[str]:
        return [w.strip() for w in self.le_highlight.text().split(',') if w.strip()]

    def selected_friends(self) -> list[str]:
        return [w.strip() for w in self.le_friends.text().split(',') if w.strip()]

    def selected_word_wrap(self) -> bool:
        return self.chk_wrap.isChecked()

    def selected_show_timestamps(self) -> bool:
        return self.chk_ts.isChecked()

    def selected_autoconnect(self) -> bool:
        return self.chk_autoc.isChecked()

    def selected_auto_negotiate(self) -> bool:
        return self.chk_auto_neg.isChecked()

    def selected_prefer_tls(self) -> bool:
        return self.chk_prefer_tls.isChecked()

    def selected_try_starttls(self) -> bool:
        return self.chk_try_starttls.isChecked()
