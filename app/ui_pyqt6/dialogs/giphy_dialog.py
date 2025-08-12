from __future__ import annotations

import json
import os
from pathlib import Path
from time import time

import requests
from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

GIPHY_SEARCH_URL = "https://api.giphy.com/v1/gifs/search"
CACHE_DIR = Path(__file__).resolve().parents[2] / "resources" / "cache"
CACHE_FILE = CACHE_DIR / "giphy_cache.json"
CACHE_TTL_SEC = 24 * 3600  # 1 day


class GiphyDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, api_key: str | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GIPHY Search")
        self.setModal(True)
        self.setMinimumSize(680, 520)
        self.selected_url: str | None = None
        self._api_key = api_key or os.getenv("GIPHY_API_KEY")
        self._cache = self._load_cache()

        root = QVBoxLayout(self)
        # API key row
        keyRow = QHBoxLayout()
        self.keyEdit = QLineEdit(self)
        self.keyEdit.setPlaceholderText("GIPHY API Key")
        # Preload from env or QSettings
        if self._api_key:
            self.keyEdit.setText(self._api_key)
        else:
            try:
                s = QSettings("DeadHop", "DeadHopClient")
                k = s.value("giphy/api_key", "", str)
                if k:
                    self._api_key = k
                    self.keyEdit.setText(k)
            except Exception:
                pass
        self.btnSaveKey = QPushButton("Save Key", self)
        self.btnSaveKey.clicked.connect(self._save_key_clicked)
        keyRow.addWidget(self.keyEdit, 1)
        keyRow.addWidget(self.btnSaveKey)
        root.addLayout(keyRow)

        # Search row
        top = QHBoxLayout()
        self.query = QLineEdit(self)
        self.query.setPlaceholderText("Search GIFs…")
        self.btnSearch = QPushButton("Search", self)
        self.btnSearch.clicked.connect(self._do_search)
        self.btnRecent = QPushButton("Recent", self)
        self.btnRecent.clicked.connect(self._show_recent)
        top.addWidget(self.query, 1)
        top.addWidget(self.btnSearch)
        top.addWidget(self.btnRecent)
        root.addLayout(top)

        # Status label
        self.status = QLabel("", self)
        self.status.setStyleSheet("color:#bbb; padding: 4px 2px;")
        root.addWidget(self.status)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.container = QWidget(self.scroll)
        self.grid = QGridLayout(self.container)
        self.grid.setContentsMargins(6, 6, 6, 6)
        self.grid.setSpacing(8)
        self.container.setLayout(self.grid)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel, self)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        self.query.returnPressed.connect(self._do_search)

        if not self._api_key:
            self.status.setText("Enter your GIPHY API key above, then press Save Key.")
        # Show recent on open if any
        self._show_recent()

    def _clear_results(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _do_search(self) -> None:
        q = (self.query.text() or "").strip()
        if not q:
            return
        # Ensure we have an API key (read from field each time)
        key = (self.keyEdit.text() or "").strip()
        if key and key != self._api_key:
            self._api_key = key
            self._persist_key(key)
        # Check cache first
        cached = self._cache.get("queries", {}).get(q)
        now = time()
        if cached and isinstance(cached, dict) and (now - cached.get("ts", 0) < CACHE_TTL_SEC):
            data = cached.get("items", [])
            self.status.setText(f"Showing cached results for ‘{q}’ ({len(data)} items)")
            self._render_results(data)
            return
        if not self._api_key:
            self.status.setText("Missing API key. Enter and Save above.")
            return
        try:
            self.status.setText(f"Searching ‘{q}’ …")
            params = {
                "api_key": self._api_key,
                "q": q,
                "limit": 24,
                "rating": "pg",
                "lang": "en",
            }
            r = requests.get(GIPHY_SEARCH_URL, params=params, timeout=10)
            r.raise_for_status()
            data = r.json().get("data", [])
            # Save to cache
            self._cache.setdefault("queries", {})[q] = {"ts": now, "items": data}
            self._save_cache()
        except Exception as e:
            self.status.setText(f"Search failed: {e}")
            return

        self.status.setText(f"Found {len(data)} results for ‘{q}’.")
        self._render_results(data)

    def _render_results(self, data) -> None:
        self._clear_results()
        row = col = 0
        for item in data or []:
            images = item.get("images", {}) if isinstance(item, dict) else {}
            # Prefer GIF url over MP4 for selection
            gif_url = (images.get("original", {}) or {}).get("url")
            mp4_url = (images.get("original_mp4", {}) or {}).get("mp4")
            select_url = gif_url or mp4_url
            if not select_url:
                continue
            # Pick a still/preview thumbnail
            thumb = None
            for key in (
                "fixed_height_small_still",
                "downsized_still",
                "fixed_width_small_still",
                "original_still",
            ):
                u = (images.get(key, {}) or {}).get("url")
                if u:
                    thumb = u
                    break
            btn = QPushButton(self.container)
            btn.setFixedSize(140, 120)
            btn.setStyleSheet(
                "QPushButton { background: #222; color: #ccc; border: 1px solid #333; border-radius: 8px; }"
            )
            vbox = QVBoxLayout()
            vbox.setContentsMargins(6, 6, 6, 6)
            vbox.setSpacing(4)
            lab = QLabel(btn)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setStyleSheet("color:#bbb")
            if thumb:
                try:
                    r = requests.get(thumb, timeout=8)
                    r.raise_for_status()
                    from PyQt6.QtCore import QByteArray
                    from PyQt6.QtGui import QPixmap

                    ba = QByteArray(r.content)
                    pm = QPixmap()
                    if pm.loadFromData(ba):
                        lab.setPixmap(
                            pm.scaled(
                                132,
                                96,
                                Qt.AspectRatioMode.KeepAspectRatio,
                                Qt.TransformationMode.SmoothTransformation,
                            )
                        )
                    else:
                        lab.setText("GIF")
                except Exception:
                    lab.setText("GIF")
            else:
                lab.setText("GIF")
            vbox.addWidget(lab, 1)
            btn.setLayout(vbox)
            btn.clicked.connect(lambda _=False, u=select_url: self._choose(u))
            self.grid.addWidget(btn, row, col)
            col += 1
            if col >= 4:
                col = 0
                row += 1
        if not data:
            self.status.setText("No results.")

    def _show_recent(self) -> None:
        recent = (self._cache.get("recent") or [])[-24:]
        data = [{"images": {"original": {"url": u}}} for u in reversed(recent)]
        self._render_results(data)
        if not recent:
            self.status.setText("No recent GIFs. Search to begin.")

    def _save_key_clicked(self) -> None:
        key = (self.keyEdit.text() or "").strip()
        if not key:
            try:
                self.status.setText("Please enter a non-empty API key.")
            except Exception:
                pass
            return
        self._api_key = key
        self._persist_key(key)
        try:
            self.status.setText("API key saved.")
        except Exception:
            pass

    def _choose(self, url: str) -> None:
        # If both mp4 and gif are known for this item, prefer gif overall.
        try:
            # When called, url is already preferred to GIF in _render_results, so just assign
            pass
        except Exception:
            pass
        self.selected_url = url
        # Update recent cache (dedupe, cap 50)
        lst = list(self._cache.get("recent") or [])
        if url in lst:
            lst.remove(url)
        lst.append(url)
        self._cache["recent"] = lst[-50:]
        self._save_cache()
        self.accept()

    # ----- Cache helpers -----
    def _load_cache(self) -> dict:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            if CACHE_FILE.exists():
                with open(CACHE_FILE, encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
        except Exception:
            pass
        return {}

    def _save_cache(self) -> None:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f)
        except Exception:
            pass

    def _persist_key(self, key: str) -> None:
        try:
            s = QSettings("DeadHop", "DeadHopClient")
            s.setValue("giphy/api_key", key)
        except Exception:
            pass


def pick_gif(parent: QWidget | None = None) -> str | None:
    dlg = GiphyDialog(parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.selected_url
    return None
