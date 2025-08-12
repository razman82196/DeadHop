from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        theme_options: list[str] | None = None,
        current_theme: str | None = None,
        opacity: float = 1.0,
        font_family: str | None = None,
        font_point_size: int | None = None,
        highlight_words: list[str] | None = None,
        friends: list[str] | None = None,
        word_wrap: bool = True,
        show_timestamps: bool = False,
        autoconnect: bool = False,
        auto_negotiate: bool = True,
        prefer_tls: bool = True,
        try_starttls: bool = False,
        # Sounds tab init values
        notify_toast: bool | None = None,
        notify_tray: bool | None = None,
        notify_sound: bool | None = None,
        presence_sound_enabled: bool | None = None,
        sound_msg_path: str | None = None,
        sound_hl_path: str | None = None,
        sound_presence_path: str | None = None,
        sound_volume: float | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        vroot = QVBoxLayout(self)
        vroot.setContentsMargins(12, 12, 12, 12)
        vroot.setSpacing(10)
        tabs = QTabWidget(self)
        vroot.addWidget(tabs, 1)

        # --- General tab ---
        pg_general = QDialog(self)
        v = QVBoxLayout(pg_general)
        v.setContentsMargins(8, 8, 8, 8)
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

        tabs.addTab(pg_general, "General")

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

        # --- Sounds tab ---
        pg_sounds = QDialog(self)
        vs = QVBoxLayout(pg_sounds)
        vs.setContentsMargins(8, 8, 8, 8)
        vs.setSpacing(10)
        form = QFormLayout()
        vs.addLayout(form)

        # Notification toggles
        row_notif = QHBoxLayout()
        self.chk_toast = QCheckBox("Toast", self)
        self.chk_tray = QCheckBox("Tray", self)
        self.chk_sound = QCheckBox("Sound", self)
        if notify_toast is not None:
            self.chk_toast.setChecked(bool(notify_toast))
        if notify_tray is not None:
            self.chk_tray.setChecked(bool(notify_tray))
        if notify_sound is not None:
            self.chk_sound.setChecked(bool(notify_sound))
        row_notif.addWidget(self.chk_toast)
        row_notif.addWidget(self.chk_tray)
        row_notif.addWidget(self.chk_sound)
        row_notif.addStretch(1)
        form.addRow("Notifications:", self._row_widget(row_notif))

        # Sound pickers
        def _mk_pick(label: str, current_path: str | None) -> tuple[QPushButton, QLineEdit]:
            le = QLineEdit(self)
            le.setReadOnly(True)
            if current_path:
                le.setText(current_path)
            btn = QPushButton("Pick…", self)
            cont = QHBoxLayout()
            cont.addWidget(le, 1)
            cont.addWidget(btn)
            form.addRow(label, self._row_widget(cont))
            return btn, le

        self.btn_pick_msg, self.le_msg = _mk_pick("Message sound:", sound_msg_path)
        self.btn_pick_hl, self.le_hl = _mk_pick("Highlight sound:", sound_hl_path)
        self.btn_pick_pr, self.le_pr = _mk_pick("Friend online:", sound_presence_path)

        def _connect_picker(btn: QPushButton, le: QLineEdit) -> None:
            def run() -> None:
                fn, _ = QFileDialog.getOpenFileName(
                    self, "Choose Sound", filter="Sounds (*.wav *.ogg)"
                )
                if fn:
                    le.setText(fn)

            btn.clicked.connect(run)

        _connect_picker(self.btn_pick_msg, self.le_msg)
        _connect_picker(self.btn_pick_hl, self.le_hl)
        _connect_picker(self.btn_pick_pr, self.le_pr)

        # Presence toggle and volume
        row_pr = QHBoxLayout()
        self.chk_presence = QCheckBox("Enable friend-online sound", self)
        if presence_sound_enabled is not None:
            self.chk_presence.setChecked(bool(presence_sound_enabled))
        row_pr.addWidget(self.chk_presence)
        row_pr.addStretch(1)
        form.addRow("Presence:", self._row_widget(row_pr))

        row_vol = QHBoxLayout()
        self.sld_vol = QSlider(Qt.Orientation.Horizontal, self)
        self.sld_vol.setRange(0, 100)
        curv = 70 if sound_volume is None else int(max(0.0, min(1.0, float(sound_volume))) * 100)
        self.sld_vol.setValue(curv)
        row_vol.addWidget(self.sld_vol)
        form.addRow("Volume:", self._row_widget(row_vol))

        tabs.addTab(pg_sounds, "Sounds")

        # Buttons
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        vroot.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        self.btn_font.clicked.connect(self._choose_font)

        self._font_family = font_family
        self._font_pt = font_point_size or 0

    def _row_widget(self, layout: QHBoxLayout) -> QWidget:
        w = QDialog(self)
        w.setLayout(layout)
        return w

    def _choose_font(self) -> None:
        font, ok = QFontDialog.getFont(parent=self)
        if ok:
            self._font_family = font.family()
            self._font_pt = font.pointSize()
            self.le_font.setText(f"{self._font_family}, {self._font_pt}pt")

    # Accessors
    def selected_theme(self) -> str | None:
        return self.cmb_theme.currentText() or None

    def selected_opacity(self) -> float:
        return float(self.sld_opacity.value()) / 100.0

    def selected_font(self) -> tuple[str | None, int | None]:
        return self._font_family, (self._font_pt or None)

    def selected_highlight_words(self) -> list[str]:
        return [w.strip() for w in self.le_highlight.text().split(",") if w.strip()]

    def selected_friends(self) -> list[str]:
        return [w.strip() for w in self.le_friends.text().split(",") if w.strip()]

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

    # Sounds tab accessors
    def selected_notify_toast(self) -> bool:
        return self.chk_toast.isChecked()

    def selected_notify_tray(self) -> bool:
        return self.chk_tray.isChecked()

    def selected_notify_sound(self) -> bool:
        return self.chk_sound.isChecked()

    def selected_presence_sound_enabled(self) -> bool:
        return self.chk_presence.isChecked()

    def selected_sound_msg(self) -> str | None:
        t = self.le_msg.text().strip()
        return t or None

    def selected_sound_hl(self) -> str | None:
        t = self.le_hl.text().strip()
        return t or None

    def selected_sound_presence(self) -> str | None:
        t = self.le_pr.text().strip()
        return t or None

    def selected_sound_volume(self) -> float:
        return float(self.sld_vol.value()) / 100.0
