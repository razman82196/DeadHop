from __future__ import annotations

from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QUrl, Qt
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    QWidget,
)


class BrowserWindow(QMainWindow):
    """A standalone in-app browser window using QWebEngineView.

    Features:
    - Persistent profile under app/resources/qtweb/browser
    - Back/Forward/Reload/Stop, URL bar, Home
    - Opens any URL passed via open_url()
    - Minimal dark theme via CSS injection script
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DeadHop – Browser")
        self.resize(1100, 800)

        # Lazy import WebEngine modules to avoid early initialization
        from PyQt6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript  # type: ignore
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # type: ignore

        # Persistent profile with explicit paths
        base = Path(__file__).resolve().parents[3] / "resources" / "qtweb" / "browser"
        cache = base / "cache"
        storage = base / "storage"
        base.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)
        storage.mkdir(parents=True, exist_ok=True)
        self.profile = QWebEngineProfile(self)
        try:
            self.profile.setCachePath(str(cache))
            self.profile.setPersistentStoragePath(str(storage))
            self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        except Exception:
            pass

        # Inject a minimal dark CSS
        css = """
        :root { color-scheme: dark; }
        ::-webkit-scrollbar { width: 10px; height: 10px; }
        ::-webkit-scrollbar-thumb { background: #3a3a3a; border-radius: 6px; }
        body { background: #121212 !important; color: #eee !important; }
        a { color: #6ab0ff !important; }
        """
        script = QWebEngineScript()
        script.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentReady)
        script.setWorldId(QWebEngineScript.ScriptWorldId.ApplicationWorld)
        script.setRunsOnSubFrames(True)
        script.setName("deadhop-dark-css")
        script.setSourceCode(
            """
            (function(){
                try {
                    let style = document.createElement('style');
                    style.type = 'text/css';
                    style.innerHTML = `%s`;
                    document.documentElement.appendChild(style);
                } catch (e) {}
            })();
            """ % css.replace("\n", " ")
        )
        self.profile.scripts().insert(script)

        # View
        self.view = QWebEngineView(self)
        try:
            self.view.page().setProfile(self.profile)
        except Exception:
            pass

        # Toolbar
        tb = QToolBar("Navigation", self)
        tb.setIconSize(tb.iconSize())
        self.addToolBar(tb)

        self.act_back = QAction(QIcon.fromTheme("go-previous"), "Back", self)
        self.act_back.triggered.connect(self.view.back)
        self.act_forward = QAction(QIcon.fromTheme("go-next"), "Forward", self)
        self.act_forward.triggered.connect(self.view.forward)
        self.act_reload = QAction(QIcon.fromTheme("view-refresh"), "Reload", self)
        self.act_reload.triggered.connect(self.view.reload)
        self.act_stop = QAction(QIcon.fromTheme("process-stop"), "Stop", self)
        self.act_stop.triggered.connect(self.view.stop)
        self.act_home = QAction(QIcon.fromTheme("go-home"), "Home", self)
        self.act_home.triggered.connect(lambda: self.open_url("https://duckduckgo.com"))

        for a in (self.act_back, self.act_forward, self.act_reload, self.act_stop, self.act_home):
            tb.addAction(a)

        # URL bar
        self.url_bar = QLineEdit(self)
        self.url_bar.setPlaceholderText("Enter URL…")
        self.url_bar.returnPressed.connect(self._on_enter_url)
        w = QWidget(self)
        lay = QHBoxLayout(w)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.addWidget(self.url_bar)
        tb.addWidget(w)

        # Central widget
        cw = QWidget(self)
        v = QVBoxLayout(cw)
        v.setContentsMargins(0, 0, 0, 0)
        v.addWidget(self.view)
        self.setCentralWidget(cw)

        # Keep URL bar in sync
        self.view.urlChanged.connect(self._sync_url)

    def _sync_url(self, url: QUrl) -> None:
        try:
            self.url_bar.setText(url.toString())
        except Exception:
            pass

    def _on_enter_url(self) -> None:
        text = self.url_bar.text().strip()
        if not text:
            return
        self.open_url(text)

    def open_url(self, url: str | QUrl) -> None:
        if isinstance(url, str):
            if not (url.startswith("http://") or url.startswith("https://")):
                url = "https://" + url
            qurl = QUrl(url)
        else:
            qurl = url
        if not qurl.isValid():
            QMessageBox.warning(self, "Invalid URL", f"Cannot open: {qurl.toString()}")
            return
        self.view.setUrl(qurl)
        self.show()
        self.activateWindow()
        self.raise_()

    # Optional cookie import API compatibility
    def import_cookies_from_system(self, domain: Optional[str] = None) -> int:
        try:
            import browser_cookie3  # type: ignore
        except Exception:
            return 0
        count = 0
        try:
            cj = browser_cookie3.load()
            for c in cj:
                if domain and (domain not in c.domain):
                    continue
                # QWebEngine cookie import requires QWebEngineCookieStore; keep simple
                count += 1
        except Exception:
            return 0
        return count
