from __future__ import annotations
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QMenu

class SidebarTree(QTreeWidget):
    channelSelected = pyqtSignal(str)
    channelAction = pyqtSignal(str, str)  # (channel, action)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setAnimated(True)
        self.setIndentation(16)
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
        root = QTreeWidgetItem([name])
        root.setFlags(root.flags() & ~Qt.ItemFlag.ItemIsSelectable)
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
            it = QTreeWidgetItem([disp])
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
            label += f"  ({count}{'!' if highlight>0 else ''})"
        it.setText(0, label)

    def _on_click(self, item: QTreeWidgetItem, _col: int) -> None:
        # Find which channel
        # Ignore top-level network nodes
        if item.parent() is None:
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
