from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont
from PyQt6.QtWidgets import QMenu, QTreeWidget, QTreeWidgetItem


class SidebarTree(QTreeWidget):
    channelSelected = pyqtSignal(str)
    channelAction = pyqtSignal(str, str)  # (channel, action)
    networkSelected = pyqtSignal(str)  # network name

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.setIndentation(16)
        # Visual flair
        self.setStyleSheet(
            """
            QTreeWidget {
                background: #0f1116;
                border: none;
            }
            QTreeWidget::item {
                height: 22px;
                padding: 3px 6px;
                border-radius: 6px;
            }
            QTreeWidget::item:selected { background: rgba(167, 139, 250, 0.22); }
            """
        )
        # Network name -> top-level item
        self._nets: dict[str, QTreeWidgetItem] = {}
        # Full label (e.g. "libera:#peach" or "[AI:llama]") -> item
        self._items: dict[str, QTreeWidgetItem] = {}
        self.itemClicked.connect(self._on_click)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._open_menu)

    def set_network(self, name: str) -> None:
        # Kept for compatibility; ensure network exists but do not clear others
        if name in self._nets:
            return
        # Emoji and color for network
        disp = f"🌐 {name}"
        root = QTreeWidgetItem([disp])
        root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        col = _hash_qcolor(name)
        root.setForeground(0, QBrush(col))
        f = QFont()
        f.setBold(True)
        root.setFont(0, f)
        self._nets[name] = root
        self.addTopLevelItem(root)
        self.expandItem(root)

    def set_channels(self, channels: list[str]) -> None:
        """Update the tree from a global list of composite labels.

        Composite format: "network:#channel". For AI entries, pass the full label (e.g. "[AI:llama]") and they will be grouped under "AI" network.
        This method is additive and also removes items that are no longer present.
        """
        desired: set[str] = set(channels or [])
        # Remove stale items
        for full, item in list(self._items.items()):
            if full not in desired:
                # detach from parent
                parent = item.parent()
                if parent is not None:
                    idx = parent.indexOfChild(item)
                    if idx >= 0:
                        parent.takeChild(idx)
                else:
                    idx = self.indexOfTopLevelItem(item)
                    if idx >= 0:
                        self.takeTopLevelItem(idx)
                del self._items[full]
        # Add missing
        for full in desired:
            if full in self._items:
                continue
            # Determine network bucket and display text
            if full.startswith("[AI:"):
                net = "AI"
                disp = full
            elif ":" in full:
                net, disp = full.split(":", 1)
            else:
                net, disp = "IRC", full
            # Ensure network root exists
            if net not in self._nets:
                self.set_network(net)
            # Emoji for channels/AI
            if net == "AI" or full.startswith("[AI:"):
                label = f"🤖 {disp}"
            else:
                label = f"💬 {disp}"
            it = QTreeWidgetItem([label])
            # Colorize channel label
            it.setForeground(0, QBrush(_hash_qcolor(full)))
            self._nets[net].addChild(it)
            self._items[full] = it
        self.expandAll()

    def set_unread(self, ch: str, count: int, highlight: int = 0) -> None:
        # ch is the composite label
        it = self._items.get(ch)
        if not it:
            return
        label = it.text(0).split("  (", 1)[0]
        if count > 0:
            label += f"  ({count}{'!' if highlight > 0 else ''})"
        it.setText(0, label)

    def _on_click(self, item: QTreeWidgetItem, _col: int) -> None:
        # Top-level: network selected
        if item.parent() is None:
            # Find which network root this is
            for net, root in self._nets.items():
                if root is item:
                    self.networkSelected.emit(net)
                    return
        # Reverse map full label
        for full, it in self._items.items():
            if it is item:
                self.channelSelected.emit(full)
                break

    def _open_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if not item or item.parent() is None:
            return
        ch = None
        for name, it in self._items.items():
            if it is item:
                ch = name
                break
        if not ch:
            return
        m = QMenu(self)
        for label in ["Open Log", "Join", "Part", "Close", "Topic", "Modes"]:
            act = m.addAction(label)
            act.triggered.connect(lambda _=False, a=label, c=ch: self.channelAction.emit(c, a))
        m.exec(self.viewport().mapToGlobal(pos))

    def select_channel(self, ch: str) -> None:
        it = self._items.get(ch)
        if it:
            self.setCurrentItem(it)


def _hash_qcolor(key: str) -> QColor:
    try:
        s = (key or "").lower().encode("utf-8")
        h = 0
        for b in s:
            h = (h * 131 + int(b)) & 0xFFFFFFFF
        hue = h % 360
        import colorsys

        r, g, b = colorsys.hls_to_rgb(hue / 360.0, 0.58, 0.62)
        return QColor(int(r * 255), int(g * 255), int(b * 255))
    except Exception:
        return QColor("#a78bfa")

    def _on_click(self, item: QTreeWidgetItem, _col: int) -> None:
        # Top-level: network selected
        if item.parent() is None:
            # Find which network root this is
            for net, root in self._nets.items():
                if root is item:
                    self.networkSelected.emit(net)
                    return
        # Reverse map full label
        for full, it in self._items.items():
            if it is item:
                self.channelSelected.emit(full)
                break

    def _open_menu(self, pos) -> None:
        item = self.itemAt(pos)
        if not item or item.parent() is None:
            return
        ch = None
        for name, it in self._items.items():
            if it is item:
                ch = name
                break
        if not ch:
            return
        m = QMenu(self)
        for label in ["Open Log", "Join", "Part", "Close", "Topic", "Modes"]:
            act = m.addAction(label)
            act.triggered.connect(lambda _=False, a=label, c=ch: self.channelAction.emit(c, a))
        m.exec(self.viewport().mapToGlobal(pos))

    def select_channel(self, ch: str) -> None:
        it = self._items.get(ch)
        if it:
            self.setCurrentItem(it)
