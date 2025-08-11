from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QDockWidget
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QDesktopServices
from pathlib import Path
from typing import Any

# Reuse the icon helper via relative import if available
try:
    from ..main_window import get_icon  # type: ignore
except Exception:
    def get_icon(names, awesome_fallback=None) -> QIcon:
        return QIcon()


class BrowserDock(QDockWidget):
    """A dockable, themed web browser using QWebEngineView with persistent profile."""

    def __init__(self, parent=None, storage_name: str = "browser") -> None:
        super().__init__("Browser", parent)
        self.setObjectName("BrowserDock")
        # Lazy import WebEngine modules now that a Q(Core)Application should exist
        from PyQt6.QtWebEngineWidgets import QWebEngineView, QWebEngineProfile  # type: ignore

        # Persistent profile under app/resources/qtweb/profile
        base = Path(__file__).resolve().parents[2] / "resources" / "qtweb" / storage_name
        base.mkdir(parents=True, exist_ok=True)
        self.profile = QWebEngineProfile(str(base))
        self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)
        self.profile.setHttpUserAgent(self.profile.httpUserAgent() + " PeachClient/1.0")

        self.view = QWebEngineView(self)
        self.view.setPage(self.profile.newPage())

        content = QWidget(self)
        self.setWidget(content)
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # Navigation bar
        bar = QWidget(content)
        hb = QHBoxLayout(bar)
        hb.setContentsMargins(6, 6, 6, 6)
        hb.setSpacing(6)

        self.btn_back = QPushButton()
        self.btn_back.setIcon(get_icon(["back", "arrow-left"], awesome_fallback="fa5s.arrow-left"))
        self.btn_back.clicked.connect(self.view.back)
        self.btn_forward = QPushButton()
        self.btn_forward.setIcon(get_icon(["forward", "arrow-right"], awesome_fallback="fa5s.arrow-right"))
        self.btn_forward.clicked.connect(self.view.forward)
        self.btn_reload = QPushButton()
        self.btn_reload.setIcon(get_icon(["reload", "refresh"], awesome_fallback="fa5s.sync"))
        self.btn_reload.clicked.connect(self.view.reload)
        self.btn_home = QPushButton()
        self.btn_home.setIcon(get_icon(["home"], awesome_fallback="fa5s.home"))
        self.btn_home.clicked.connect(self._go_home)
        self.btn_ext = QPushButton()
        self.btn_ext.setIcon(get_icon(["external", "open"], awesome_fallback="fa5s.external-link-alt"))
        self.btn_ext.clicked.connect(self._open_external)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Enter URL and press Enter…")
        self.url_edit.returnPressed.connect(self._load_from_edit)

        hb.addWidget(self.btn_back)
        hb.addWidget(self.btn_forward)
        hb.addWidget(self.btn_reload)
        hb.addWidget(self.btn_home)
        hb.addWidget(self.url_edit, 1)
        hb.addWidget(self.btn_ext)

        v.addWidget(bar, 0)
        v.addWidget(self.view, 1)

        # Apply dark theme tweaks via CSS injection on load
        self.view.loadFinished.connect(self._inject_theme)

        # Default home
        self.home_url = QUrl("https://www.example.com/")
        self.view.setUrl(self.home_url)

    # --- Slots ---
    def _go_home(self) -> None:
        self.view.setUrl(self.home_url)

    def _open_external(self) -> None:
        QDesktopServices.openUrl(self.view.url())

    def _load_from_edit(self) -> None:
        text = self.url_edit.text().strip()
        if not text:
            return
        if not (text.startswith("http://") or text.startswith("https://")):
            text = "https://" + text
        self.view.setUrl(QUrl(text))

    def _inject_theme(self, ok: bool) -> None:
        if not ok:
            return
        # Minimal dark style; sites may override. This helps integrate with qt-material.
        js = """
        (function(){
            try {
                const s = document.createElement('style');
                s.id = 'peach-dark';
                s.textContent = `
                    html, body { background: #121212 !important; color: #e0e0e0 !important; }
                    a { color: #82b1ff !important; }
                    ::-webkit-scrollbar { width: 10px; height: 10px; }
                    ::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 6px; }
                    ::-webkit-scrollbar-track { background: #121212; }
                `;
                document.documentElement.appendChild(s);
            } catch(e) {}
        })();
        """
        self.view.page().runJavaScript(js)

    # --- Optional cookie import from system browsers ---
    def import_cookies_from_system(self, domain: str) -> int:
        """Attempt to import cookies for a given domain from the default system browsers.

        Returns number of cookies imported. Requires 'browser-cookie3' to be installed.
        """
        try:
            import browser_cookie3  # type: ignore
        except Exception:
            return 0
        total = 0
        # Import core module lazily here as well
        from PyQt6.QtWebEngineCore import QWebEngineCookieStore  # type: ignore
        store: Any = self.profile.cookieStore()
        def add_cookie(c):
            from PyQt6.QtNetwork import QNetworkCookie
            try:
                qc = QNetworkCookie()
                qc.setName(c.name.encode())
                qc.setValue(c.value.encode())
                qc.setDomain(c.domain)
                qc.setPath(c.path or "/")
                # Expiry not strictly required; session cookies are fine
                store.setCookie(qc)
                return True
            except Exception:
                return False
        try:
            for getter in (browser_cookie3.chrome, browser_cookie3.edge, browser_cookie3.firefox):
                try:
                    jar = getter(domain_name=domain)
                    for c in jar:
                        if add_cookie(c):
                            total += 1
                except Exception:
                    continue
        except Exception:
            pass
        return total
