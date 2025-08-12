from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel
from typing import Optional


class VideoPanel(QWidget):
    """Inline, resizable video player for YouTube embeds."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("VideoPanel")
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)

        # Header row with title and controls
        header = QWidget(self)
        hb = QHBoxLayout(header)
        hb.setContentsMargins(6, 4, 6, 4)
        hb.setSpacing(6)
        self.lbl = QLabel("YouTube Player", header)
        self.btn_pop = QPushButton("Open in Browser", header)
        self.btn_close = QPushButton("Close", header)
        hb.addWidget(self.lbl, 1)
        hb.addWidget(self.btn_pop)
        hb.addWidget(self.btn_close)
        v.addWidget(header, 0)

        # Lazy import to ensure QApplication and WebEngine are initialized
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # type: ignore
        from PyQt6.QtWebEngineCore import QWebEnginePage  # type: ignore
        class _VidPage(QWebEnginePage):
            def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
                try:
                    m = str(message)
                    src = str(sourceID)
                    noisy = (
                        'requestStorageAccessFor',
                        'generate_204',
                        'googleads.g.doubleclick.net',
                        'CORS policy',
                        'ResizeObserver loop completed',
                    )
                    if any(s in m or s in src for s in noisy):
                        return
                except Exception:
                    pass
                try:
                    super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)
                except Exception:
                    pass
        self.view = QWebEngineView(self)
        try:
            self.view.setPage(_VidPage(self))
        except Exception:
            pass
        v.addWidget(self.view, 1)

        self._current_url = ""

        self.btn_close.clicked.connect(self.hide)
        # pop-out will be wired by MainWindow after creation via set_pop_handler
        self._pop_handler = None
        self.btn_pop.clicked.connect(self._do_pop)

        self.hide()

    def _do_pop(self) -> None:
        if self._pop_handler and callable(self._pop_handler):
            try:
                self._pop_handler(self._current_url)
            except Exception:
                pass

    def set_pop_handler(self, fn) -> None:
        self._pop_handler = fn

    def stop(self) -> None:
        try:
            # Load about:blank to stop playback
            self.view.setUrl(QUrl("about:blank"))
        except Exception:
            pass

    def play_youtube_id(self, video_id: str, autoplay: bool = True) -> None:
        """Load a YouTube embed by ID."""
        if not video_id:
            return
        url = f"https://www.youtube.com/embed/{video_id}?rel=0&modestbranding=1&autohide=1&showinfo=0{'&autoplay=1' if autoplay else ''}"
        self._current_url = f"https://www.youtube.com/watch?v={video_id}"
        try:
            self.view.setUrl(QUrl(url))
            self.show()
        except Exception:
            pass
