from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QPoint, QSettings, Qt
from PyQt6.QtGui import QIcon, QPalette
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
)

from .server_editor_dialog import ServerEditorDialog
from app.ui_pyqt6.delegates.elide_delegate import ElideDelegate


class WelcomeDialog(QDialog):
    """DeadHop branded welcome/splash dialog.

    Lets the user:
      - Pick and connect to a saved server
      - Add/Edit/Delete saved servers
      - Choose an AI model and whether to enable it for this session
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Welcome to DeadHop")
        self.setModal(True)

        # Frameless window that can be styled
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # Ensure it has a visible footprint
        self.setMinimumSize(600, 460)

        # Root layout (compact, responsive)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # Themed card container (inherits palette from qt-material)
        card = QFrame(self)
        card.setObjectName("WelcomeCard")
        card.setFrameShape(QFrame.Shape.NoFrame)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._apply_card_style(card)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        # Soft drop shadow on the card
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(self.palette().color(QPalette.ColorRole.Shadow))
        card.setGraphicsEffect(shadow)

        # Branding header
        header = QHBoxLayout()
        header.setSpacing(10)
        icon_label = QLabel()
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = self._app_icon()
        if not icon.isNull():
            logical = self.fontMetrics().height() * 4
            icon_label.setPixmap(icon.pixmap(logical, logical))
        header.addWidget(icon_label)

        branding = QVBoxLayout()
        branding.setSpacing(2)
        title = QLabel("DeadHop")
        title_font = self.font()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        branding.addWidget(title)
        subtitle = QLabel("Fast. Minimal. IRC that slaps.")
        branding.addWidget(subtitle)
        header.addLayout(branding)
        card_layout.addLayout(header)

        # ----- Saved Servers -----
        srv_box = QGroupBox("SAVED SERVERS")
        srv_layout = QGridLayout(srv_box)
        srv_layout.setContentsMargins(8, 8, 8, 8)
        srv_layout.setHorizontalSpacing(8)
        srv_layout.setVerticalSpacing(6)
        self.server_list = QListWidget()
        self.server_list.setItemDelegate(ElideDelegate(self.server_list))
        self.server_list.setUniformItemSizes(True)
        self.server_list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        srv_layout.addWidget(self.server_list, 0, 0, 4, 1)

        btns_col = QVBoxLayout()
        btns_col.setSpacing(6)
        self.btn_add = QPushButton("+")
        self.btn_add.setToolTip("Add a new server")
        self.btn_edit = QPushButton(
            self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView), " Edit"
        )
        # self.btn_edit enabled by default
        self.btn_del = QPushButton("-")
        self.btn_del.setToolTip("Delete selected server")
        self.btn_connect = QPushButton("Connect")
        # Apply styling classes now that buttons exist
        try:
            self.btn_connect.setProperty("class", "primary")
            self.btn_add.setProperty("class", "secondary")
            self.btn_edit.setProperty("class", "secondary")
            self.btn_del.setProperty("class", "danger")
        except Exception:
            pass
        btns_col.addWidget(self.btn_add)
        btns_col.addWidget(self.btn_edit)
        btns_col.addWidget(self.btn_del)
        btns_col.addStretch(1)
        btns_col.addWidget(self.btn_connect)
        srv_layout.addLayout(btns_col, 0, 1, 4, 1)
        card_layout.addWidget(srv_box)

        # ----- AI Assistant -----
        ai_box = QGroupBox("AI ASSISTANT (OLLAMA)")
        ai_layout = QGridLayout(ai_box)
        ai_layout.setContentsMargins(8, 8, 8, 8)
        ai_layout.setHorizontalSpacing(8)
        ai_layout.setVerticalSpacing(6)
        ai_layout.addWidget(QLabel("Model:"), 0, 0)
        self.cmb_model = QComboBox()
        self.cmb_model.setEditable(True)
        self.cmb_model.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ai_layout.addWidget(self.cmb_model, 0, 1)
        self.chk_ai = QCheckBox("Enable AI this session")
        ai_layout.addWidget(self.chk_ai, 1, 0, 1, 2)
        card_layout.addWidget(ai_box)

        # ----- Dialog buttons -----
        self.dbb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self._style_primary_button()
        card_layout.addWidget(self.dbb)

        root.addWidget(card)

        # ----- Load data and wire signals -----
        self._load_ai_prefs()
        self._populate_servers()
        self._wire_signals()

        # Center on the active screen (after sizing)
        try:
            self.adjustSize()
            geo = self.frameGeometry()
            scr = self.screen()
            if scr is not None:
                geo.moveCenter(scr.availableGeometry().center())
                self.move(geo.topLeft())
        except Exception:
            pass

    # ----- Public API -----
    @property
    def selected_server_name(self) -> str | None:
        if (items := self.server_list.selectedItems()) and items:
            return items[0].data(Qt.ItemDataRole.UserRole)
        return None

    @property
    def ai_enabled(self) -> bool:
        return self.chk_ai.isChecked()

    @property
    def ai_model(self) -> str:
        return self.cmb_model.currentText()

    # ----- Setup & Teardown -----
    def _wire_signals(self) -> None:
        self.btn_add.clicked.connect(self._on_add)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_del.clicked.connect(self._on_delete)
        self.btn_connect.clicked.connect(self.accept)
        self.server_list.itemDoubleClicked.connect(self.accept)
        self.dbb.accepted.connect(self.accept)
        self.dbb.rejected.connect(self.reject)

    def accept(self) -> None:
        self.persist_ai_prefs()
        super().accept()

    def reject(self) -> None:
        self.persist_ai_prefs()
        super().reject()

    # ----- Data Loading & Persistence -----
    def _app_icon(self) -> QIcon:
        p = Path(__file__).parent.parent.parent / "assets/icon.png"
        if p.exists():
            return QIcon(str(p))
        return QIcon()

    def _populate_servers(self) -> None:
        self.server_list.clear()
        s = QSettings("DeadHop", "DeadHopClient")
        names = s.value("servers/names", [], list) or []
        for name in names:
            base = f"servers/{name}"
            host = s.value(f"{base}/host", "", str) or ""
            port = int(s.value(f"{base}/port", 6697))
            display_text = f"{name}  —  {host}:{port}"
            item = QListWidgetItem(display_text)
            item.setToolTip(display_text)
            item.setData(Qt.ItemDataRole.UserRole, name)
            self.server_list.addItem(item)
        if self.server_list.count() > 0:
            self.server_list.setCurrentRow(0)

    def _load_ai_prefs(self) -> None:
        s = QSettings("DeadHop", "DeadHopClient")
        model = s.value("ai/model", "llama3", str) or "llama3"
        enabled = s.value("ai/enabled", False, bool)
        i = self.cmb_model.findText(model)
        if i >= 0:
            self.cmb_model.setCurrentIndex(i)
        else:
            self.cmb_model.setEditText(model)
        self.chk_ai.setChecked(enabled)

    def persist_ai_prefs(self) -> None:
        s = QSettings("DeadHop", "DeadHopClient")
        s.setValue("ai/model", self.ai_model)
        s.setValue("ai/enabled", self.ai_enabled)

    # ----- Event Handlers -----
    def _on_add(self) -> None:
        dlg = ServerEditorDialog(self)
        if dlg.exec():
            self._populate_servers()
            # Select the newly added server
            for i in range(self.server_list.count()):
                if self.server_list.item(i).data(Qt.ItemDataRole.UserRole) == dlg.name:
                    self.server_list.setCurrentRow(i)
                    break

    def _on_edit(self) -> None:
        name = self.selected_server_name
        if not name:
            return
        dlg = ServerEditorDialog(self, name)
        if dlg.exec():
            self._populate_servers()
            # Reselect the edited server
            for i in range(self.server_list.count()):
                if self.server_list.item(i).data(Qt.ItemDataRole.UserRole) == dlg.name:
                    self.server_list.setCurrentRow(i)
                    break

    def _on_delete(self) -> None:
        name = self.selected_server_name
        if not name:
            return

        if (
            QMessageBox.question(
                self,
                "Delete Server",
                f"Remove saved server '{name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            != QMessageBox.StandardButton.Yes
        ):
            return

        s = QSettings("DeadHop", "DeadHopClient")
        names = [n for n in (s.value("servers/names", [], list) or []) if n != name]
        s.setValue("servers/names", names)
        s.remove(f"servers/{name}")
        self._populate_servers()

    # ----- Styling Helpers -----
    def _apply_card_style(self, w: QFrame) -> None:
        """Style the inner card with a Discord-like theme."""
        # Discord color palette
        bg = "#36393f"
        border = "#202225"
        text = "#dcddde"
        highlight = "#5865F2"
        base = "#ffffff"
        danger = "#ed4245"
        secondary_bg = "#4f545c"
        input_bg = "#2f3136"

        w.setStyleSheet(
            f"""#WelcomeCard {{
                background: {bg};
                border-radius: 8px;
                border: 1px solid {border};
            }}
            #WelcomeCard QGroupBox {{ color: #b9bbbe; font-weight: 600; margin-top: 8px; }}
            #WelcomeCard QGroupBox::title {{ subcontrol-origin: margin; left: 6px; padding: 0 2px; }}
            #WelcomeCard QLabel {{ color: {text}; }}
            #WelcomeCard QListWidget {{
                background: {input_bg};
                border: 1px solid {border};
                border-radius: 4px;
            }}
            #WelcomeCard QListWidget::item {{ color: {text}; padding: 4px; }}
            #WelcomeCard QListWidget::item:selected {{
                background: {highlight};
                color: {base};
            }}
            #WelcomeCard QPushButton {{
                border-radius: 4px;
                padding: 8px 12px;
                font-weight: 500;
                border: none;
            }}
            #WelcomeCard QPushButton[class='primary'] {{ background: {highlight}; color: {base}; }}
            #WelcomeCard QPushButton[class='secondary'] {{ background: {secondary_bg}; color: {text}; }}
            #WelcomeCard QPushButton[class='danger'] {{ background: {danger}; color: {base}; }}
            #WelcomeCard QComboBox, #WelcomeCard QComboBox QLineEdit {{
                background: {input_bg};
                color: {text};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 4px;
            }}
            #WelcomeCard QCheckBox {{ color: {text}; }}
            """
        )
        # Do not touch button properties here; buttons may not yet exist

    def _style_primary_button(self) -> None:
        ok = self.dbb.button(QDialogButtonBox.StandardButton.Ok)
        if ok:
            ok.setText("OK / Connect")
            ok.setDefault(True)
            ok.setAutoDefault(True)
            ok.setProperty("class", "primary")
        cancel = self.dbb.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel:
            cancel.setProperty("class", "secondary")

    # ----- Drag support for frameless window -----
    def mousePressEvent(self, e: QPoint) -> None:
        if e.buttons() & Qt.MouseButton.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e: QPoint) -> None:
        if (e.buttons() & Qt.MouseButton.LeftButton) and hasattr(self, "_drag_pos"):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
