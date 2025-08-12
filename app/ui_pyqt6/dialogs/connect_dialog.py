from __future__ import annotations

import random

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QVBoxLayout,
)


class ConnectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to IRC")
        self.resize(380, 220)
        v = QVBoxLayout(self)
        form = QFormLayout()
        self.host = QLineEdit("irc.libera.chat")
        self.port = QLineEdit("6697")
        self.tls = QCheckBox("Use TLS")
        self.tls.setChecked(True)
        # Default nick: DeadRabbit + random 4-digit number
        self.nick = QLineEdit(self._rand_nick())
        self.user = QLineEdit("peach")
        self.realname = QLineEdit("DeadHop")
        self.channels = QLineEdit("#peach,#python")
        self.password = QLineEdit("")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.sasl_user = QLineEdit("")
        # Remember + Autoconnect toggles
        toggles = QHBoxLayout()
        self.remember = QCheckBox("Remember server")
        self.autoconnect = QCheckBox("Auto-connect")
        toggles.addWidget(self.remember)
        toggles.addWidget(self.autoconnect)
        form.addRow("Host", self.host)
        form.addRow("Port", self.port)
        form.addRow("", self.tls)
        form.addRow("Nick", self.nick)
        form.addRow("User", self.user)
        form.addRow("Real name", self.realname)
        form.addRow("Channels", self.channels)
        form.addRow("Password (NickServ/SASL)", self.password)
        form.addRow("SASL User (optional)", self.sasl_user)
        form.addRow("", self.remember)
        form.addRow("", self.autoconnect)
        v.addLayout(form)
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        v.addWidget(btns)

    def values(self):
        host = self.host.text().strip() or "irc.libera.chat"
        try:
            port = int(self.port.text().strip() or "6697")
        except Exception:
            port = 6697
        tls = self.tls.isChecked()
        # Fallback to a fresh random nick if empty
        nick = self.nick.text().strip() or self._rand_nick()
        user = self.user.text().strip() or "peach"
        realname = self.realname.text().strip() or "DeadHop"
        chans = [c.strip() for c in (self.channels.text().strip() or "").split(",") if c.strip()]
        password = self.password.text().strip() or None
        sasl_user = self.sasl_user.text().strip() or None
        remember = self.remember.isChecked()
        autoconnect = self.autoconnect.isChecked()
        return (
            host,
            port,
            tls,
            nick,
            user,
            realname,
            chans,
            password,
            sasl_user,
            remember,
            autoconnect,
        )

    def _rand_nick(self) -> str:
        try:
            return f"DeadRabbit{random.randint(1000, 9999)}"
        except Exception:
            return "DeadRabbit0000"
