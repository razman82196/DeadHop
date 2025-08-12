from __future__ import annotations

import asyncio
import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

URL_RE = re.compile(r"\bhttps?://[\w\-._~:/?#\[\]@!$&'()*+,;=%]+", re.IGNORECASE)

try:
    import httpx
    from bs4 import BeautifulSoup
except Exception:  # optional
    httpx = None
    BeautifulSoup = None


class URLGrabber(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(6)
        self.list = QListWidget(self)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._open_menu)
        v.addWidget(self.list, 1)
        h = QHBoxLayout()
        self.btn_clear = QPushButton("Clear", self)
        self.btn_copy = QPushButton("Copy All", self)
        h.addWidget(self.btn_clear)
        h.addWidget(self.btn_copy)
        v.addLayout(h)
        self.btn_clear.clicked.connect(self.list.clear)
        self.btn_copy.clicked.connect(self._copy)

        self._seen: set[str] = set()
        self._sem = asyncio.Semaphore(4)  # limit concurrent fetches

    def add_from_text(self, text: str) -> None:
        for url in URL_RE.findall(text or ""):
            if url in self._seen:
                continue
            self._seen.add(url)
            item = QListWidgetItem(url, self.list)
            # schedule title fetch
            if httpx and BeautifulSoup:
                try:
                    asyncio.create_task(self._fetch_title(url, item))
                except Exception:
                    pass

    async def _fetch_title(self, url: str, item: QListWidgetItem) -> None:
        async with self._sem:
            try:
                timeout = httpx.Timeout(5.0, connect=5.0, read=5.0) if httpx else None
                async with httpx.AsyncClient(
                    follow_redirects=True,
                    timeout=timeout,
                    headers={"User-Agent": "DeadHopClient/1.0"},
                ) as client:
                    r = await client.get(url)
                    if r.status_code >= 400:
                        return
                    soup = BeautifulSoup(r.text, "lxml") if BeautifulSoup else None
                    title: str | None = None
                    if soup is not None:
                        t = soup.find("title")
                        if t and t.text:
                            title = t.text.strip()
                    if title:
                        item.setText(f"{title} — {url}")
            except Exception:
                # ignore failures silently
                pass

    def _open_menu(self, pos) -> None:
        it = self.list.itemAt(pos)
        if not it:
            return
        m = QMenu(self)
        act_open = m.addAction("Open")
        act_copy = m.addAction("Copy")
        chosen = m.exec(self.list.mapToGlobal(pos))
        if not chosen:
            return
        text = it.text()
        # the URL is after ' — ' if title exists
        url = text.split(" — ")[-1]
        if chosen is act_open:
            from PyQt6.QtCore import QUrl
            from PyQt6.QtGui import QDesktopServices

            QDesktopServices.openUrl(QUrl(url))
        elif chosen is act_copy:
            from PyQt6.QtWidgets import QApplication

            QApplication.clipboard().setText(url)

    def _copy(self) -> None:
        from PyQt6.QtWidgets import QApplication

        items = [self.list.item(i).text() for i in range(self.list.count())]
        QApplication.clipboard().setText("\n".join(items))
