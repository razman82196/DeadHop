from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QIntValidator
from PyQt6.QtCore import QSettings


class ServerEditorDialog(QDialog):
    """
    Add/Edit a saved server profile stored in QSettings under keys:
      - servers/names: list[str]
      - servers/<name>/{host,port,tls,channels,password,sasl_user,ignore_invalid_certs}
    """

    def __init__(self, parent: QWidget | None = None, name: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Server Details")
        self.setModal(True)
        self.name_original = name or ""

        self.ed_name = QLineEdit()
        self.ed_host = QLineEdit()
        self.ed_port = QSpinBox()
        self.ed_port.setRange(1, 65535)
        self.ed_port.setValue(6697)
        self.chk_tls = QCheckBox("Use TLS (SSL)")
        self.ed_channels = QLineEdit()
        self.ed_password = QLineEdit()
        self.ed_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_sasl_user = QLineEdit()
        self.chk_ignore_invalid = QCheckBox("Ignore invalid TLS certificates")

        form = QFormLayout()
        form.addRow("Profile name", self.ed_name)
        form.addRow("Host", self.ed_host)
        form.addRow("Port", self.ed_port)
        form.addRow("Channels (comma-separated)", self.ed_channels)
        form.addRow("Password (optional)", self.ed_password)
        form.addRow("SASL user (optional)", self.ed_sasl_user)
        form.addRow("", self.chk_tls)
        form.addRow("", self.chk_ignore_invalid)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_accept)
        btns.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addLayout(form)
        lay.addWidget(btns)

        if self.name_original:
            self._load_into_fields(self.name_original)

    # ----- Properties -----
    @property
    def name(self) -> str:
        return (self.ed_name.text() or "").strip()

    # ----- Internals -----
    def _load_into_fields(self, name: str) -> None:
        s = QSettings("DeadHop", "DeadHopClient")
        base = f"servers/{name}"
        self.ed_name.setText(name)
        self.ed_host.setText(s.value(f"{base}/host", "", str) or "")
        try:
            self.ed_port.setValue(int(s.value(f"{base}/port", 6697)))
        except Exception:
            self.ed_port.setValue(6697)
        self.chk_tls.setChecked(bool(s.value(f"{base}/tls", True, bool)))
        self.ed_channels.setText(s.value(f"{base}/channels", "", str) or "")
        self.ed_password.setText(s.value(f"{base}/password", "", str) or "")
        self.ed_sasl_user.setText(s.value(f"{base}/sasl_user", "", str) or "")
        self.chk_ignore_invalid.setChecked(
            bool(s.value(f"{base}/ignore_invalid_certs", False, bool))
        )

    def _on_accept(self) -> None:
        name = self.name
        host = (self.ed_host.text() or "").strip()
        port = int(self.ed_port.value())
        if not name:
            QMessageBox.warning(self, "Missing name", "Please enter a profile name.")
            return
        if not host:
            QMessageBox.warning(self, "Missing host", "Please enter a server host.")
            return

        s = QSettings("DeadHop", "DeadHopClient")
        names: list[str] = s.value("servers/names", [], list) or []
        # Handle rename: if new name collides with different existing, block
        if name != self.name_original and name in names:
            QMessageBox.warning(
                self,
                "Name exists",
                f"A profile named '{name}' already exists. Choose a different name.",
            )
            return

        # Persist details
        base = f"servers/{name}"
        s.setValue(f"{base}/host", host)
        s.setValue(f"{base}/port", port)
        s.setValue(f"{base}/tls", bool(self.chk_tls.isChecked()))
        s.setValue(f"{base}/channels", (self.ed_channels.text() or "").strip())
        s.setValue(f"{base}/password", self.ed_password.text())
        s.setValue(f"{base}/sasl_user", (self.ed_sasl_user.text() or "").strip())
        s.setValue(f"{base}/ignore_invalid_certs", bool(self.chk_ignore_invalid.isChecked()))
        # Update names list
        if name not in names:
            names.append(name)
        if self.name_original and self.name_original != name:
            # remove old record
            try:
                s.remove(f"servers/{self.name_original}")
                names = [n for n in names if n != self.name_original]
                names.append(name)
            except Exception:
                pass
        s.setValue("servers/names", names)

        self.accept()
