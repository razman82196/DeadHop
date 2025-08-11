from __future__ import annotations
import re
import shutil
from typing import Optional

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence, QTextCursor, QCursor, QFont, QIcon, QTextDocument
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMainWindow, QDockWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QListWidget, QListWidgetItem, QLabel,
    QFileDialog, QMessageBox, QInputDialog, QToolBar, QMenuBar,
    QMenu, QDialog, QDialogButtonBox, QCheckBox, QSplitter, QTextBrowser, QStatusBar,
    QListWidget, QPushButton,
)
from PyQt6.QtGui import QDesktopServices, QAction
from PyQt6.QtCore import QUrl
import asyncio
import re
import time
from PyQt6.QtCore import QSettings, QByteArray, QSize, QUrl
import asyncio
import re
import time
from PyQt6.QtCore import QThread
from .widgets.composer import Composer
from .widgets.members_view import MembersView
from .widgets.toast import ToastHost
from .widgets.sidebar_tree import SidebarTree
from .widgets.url_grabber import URLGrabber
from .widgets.find_bar import FindBar
from .widgets.friends_dock import FriendsDock
from .bridge import BridgeQt
from .ai_worker import OllamaStreamWorker
from ..ai.ollama import is_server_up
from PyQt6.QtCore import QThread
from .dialogs.connect_dialog import ConnectDialog
from .dialogs.topic_dialog import TopicDialog
from .dialogs.modes_dialog import ModesDialog
try:
    from .theme import theme_manager as _theme_manager
except Exception:
    _theme_manager = None
from ..logging.log_writer import LogWriter
from pathlib import Path

# --- Icon utilities ---
# Prefer filesystem icons placed under `app/resources/icons/custom/`.
_ICONS_DIR = Path(__file__).resolve().parents[1] / "resources" / "icons"
_CUSTOM_ICONS_DIR = _ICONS_DIR / "custom"

def _icon_from_fs(name: str) -> QIcon:
    """Try to load an icon by base name from the custom icons folder.

    Tries common name variants and file extensions.
    """
    if not name:
        return QIcon()
    variants = {
        name,
        name.lower(),
        name.replace(" ", "_").lower(),
        name.replace(" ", "-").lower(),
    }
    exts = (".svg", ".png", ".ico", ".jpg", ".jpeg", ".bmp", ".webp")
    try:
        for base in variants:
            for ext in exts:
                p = _CUSTOM_ICONS_DIR / f"{base}{ext}"
                if p.exists():
                    return QIcon(str(p))
    except Exception:
        pass
    return QIcon()

def get_icon(names: list[str] | tuple[str, ...], awesome_fallback: str | None = None) -> QIcon:
    """Resolve an icon preferring theme (qtawesome), then filesystem as fallback.

    names: ordered list of candidate base names (without extension).
    awesome_fallback: qtawesome name like 'fa5s.plug' (optional).
    """
    # Prefer themed icon via qtawesome if provided
    if awesome_fallback:
        try:
            import qtawesome as qta
            ic = qta.icon(awesome_fallback)
            if ic and not ic.isNull():
                return ic
        except Exception:
            pass
    # Filesystem fallback (custom overrides)
    try:
        for n in names:
            ic = _icon_from_fs(n)
            if not ic.isNull():
                return ic
    except Exception:
        pass
    return QIcon()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Peach Client (PyQt6)")
        self.resize(1200, 800)
        self.bridge = BridgeQt()
        # Notification preferences (defaults)
        self._notify_on_pm = True
        self._notify_on_mention = True
        self._notify_on_highlight = True
        self._notify_on_join_part = True
        # Apply default theme (prefer qt-material; fallback to legacy theme manager if present)
        try:
            from PyQt6.QtWidgets import QApplication
            from qt_material import apply_stylesheet, list_themes
            app = QApplication.instance()
            if app:
                themes = list_themes()
                preferred = "dark_teal.xml"
                theme = preferred if preferred in themes else (themes[0] if themes else None)
                if theme:
                    apply_stylesheet(app, theme=theme)
        except Exception:
            if _theme_manager is not None:
                try:
                    _theme_manager().apply()
                except Exception:
                    pass
        # Per-channel logger
        self.logger = LogWriter()
        # Highlights and sounds
        self._highlight_keywords: list[str] = []  # defaults to nick later
        self._sound_enabled: bool = True
        try:
            from PyQt6.QtMultimedia import QSoundEffect
            self._sound = QSoundEffect(self)
            self._sound.setSource(QUrl.fromLocalFile("") )  # lazy set later or system sound
        except Exception:
            self._sound = None

        # Central area: sidebar | chat | members using splitters
        central = QWidget(self)
        self.setCentralWidget(central)
        root_v = QVBoxLayout(central)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        # Top toolbar removed per UI simplification

        # Sidebar tree (Network > Channels)
        self.sidebar = SidebarTree()
        self.sidebar.channelSelected.connect(self._on_channel_clicked)
        self.sidebar.channelAction.connect(self._on_channel_action)

        # Chat view (rich text for now)
        self.chat = QTextBrowser()
        self.chat.setOpenExternalLinks(True)
        self.chat.setPlaceholderText("Welcome to Peach. Select a channel to start chatting…")

        # Composer
        self.composer = Composer()
        self.composer.messageSubmitted.connect(self._on_submit)

        # Members
        self.members = MembersView()
        self.members.memberAction.connect(self._on_member_action)

        # Splitter layout
        self.split_lr = QSplitter(Qt.Orientation.Horizontal)
        self.split_lr.addWidget(self.sidebar)
        self.split_lr.addWidget(self.chat)
        self.split_lr.addWidget(self.members)
        self.split_lr.setStretchFactor(0, 0)
        self.split_lr.setStretchFactor(1, 1)
        self.split_lr.setStretchFactor(2, 0)
        self.split_lr.setSizes([240, 800, 240])

        # Assemble center
        center = QWidget()
        center_v = QVBoxLayout(center)
        center_v.setContentsMargins(8, 8, 8, 8)
        center_v.setSpacing(8)
        center_v.addWidget(self.split_lr, 1)
        center_v.addWidget(self.composer, 0)

        root_v.addWidget(center)

        # Status bar + toast host
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.toast_host = ToastHost(self)

        # IRC Log dock
        self.log_view = QTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_dock = QDockWidget("IRC Log", self)
        self.log_dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()

        # URL Grabber dock
        self.url_grabber = URLGrabber(self)
        self.url_dock = QDockWidget("URLs", self)
        self.url_dock.setWidget(self.url_grabber)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.url_dock)
        self.url_dock.hide()

        # Browser dock (integrated WebEngine) - created lazily
        self.browser_dock: Optional[QDockWidget] = None

        # Find bar dock
        self.find_bar = FindBar(self)
        self.find_bar.searchRequested.connect(self._on_find)
        self.find_dock = QDockWidget("Find", self)
        self.find_dock.setWidget(self.find_bar)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.find_dock)
        self.find_dock.hide()

        # Friends dock (MONITOR)
        self.friends = FriendsDock(self)
        self.friends_dock = QDockWidget("Friends", self)
        self.friends_dock.setWidget(self.friends)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.friends_dock)
        self.friends_dock.hide()

        # Servers dock (initialized on demand)
        self.servers_dock = None
        # Browser dock (initialized on demand; keep None until created)
        self.browser_dock = None
        # Track which saved server (by name) we connected to, for persistence
        self._current_server_name: str | None = None
        # AI routing defaults to avoid AttributeError before first use
        self._ai_route_target = None
        self._ai_accum = ""
        self._ai_stream_open = False
        # Channel and unread/highlight tracking structures
        self._channel_labels: list[str] = []
        self._unread: dict[str, int] = {}
        self._highlights: dict[str, int] = {}

        # Menus
        self._build_menus()
        # Toolbar removed

        # Bridge signal wiring
        self.bridge.statusChanged.connect(self._on_status)
        self.bridge.messageReceived.connect(self._on_message)
        self.bridge.namesUpdated.connect(self._on_names)
        self.bridge.currentChannelChanged.connect(self._on_current_channel_changed)
        self.bridge.channelsUpdated.connect(self._on_channels_updated)

        # Apply saved settings and maybe autoconnect
        try:
            self._load_settings()
            self._apply_settings()
        except Exception:
            pass
        try:
            self._maybe_autoconnect_from_settings()
        except Exception:
            pass

        # Unread/highlight counters
        self._unread: dict[str, int] = {}
        self._highlights: dict[str, int] = {}
        # Apply global rounded corners styling overlay
        try:
            self._apply_rounded_corners(8)
        except Exception:
            pass
        # 

    def _schedule_async(self, func, *args, **kwargs) -> None:
        """Schedule a callable; if it returns a coroutine, create a task."""
        def runner() -> None:
            try:
                res = func(*args, **kwargs)
                # If coroutine, schedule it; if Task/future, do nothing
                if asyncio.iscoroutine(res):
                    asyncio.create_task(res)
            except Exception:
                pass
        try:
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, runner)
        except Exception:
            runner()

    # ----- Member actions -----

    # ----- Member actions -----
    def _on_member_action(self, nick: str, action: str) -> None:
        action = action.lower()
        if action == "whois":
            # Try to send raw WHOIS if bridge supports it
            sent = False
            for meth in ("sendRaw", "sendCommand"):
                fn = getattr(self.bridge, meth, None)
                if callable(fn):
                    try:
                        fn(f"WHOIS {nick}")
                        sent = True
                        break
                    except Exception:
                        pass
            if not sent:
                self.chat.append(f"<i>WHOIS {nick} (not sent: no raw command API)</i>")
        elif action == "query":
            label = f"[PM:{nick}]"
            # Ensure PM label exists in sidebar without wiping existing channels
            try:
                if label not in self._channel_labels:
                    self._channel_labels.append(label)
                    self.sidebar.set_channels(self._channel_labels)
                    self.sidebar.set_unread(label, 0, 0)
            except Exception:
                pass
            try:
                self.bridge.set_current_channel(label)
            except Exception:
                pass
        elif action == "kick":
            ch = self.bridge.current_channel() or ""
            reason, ok = QInputDialog.getText(self, "Kick", f"Reason for kicking {nick} from {ch}:", text="")
            if ok:
                sent = False
                for meth, cmd in (("kickUser", None), ("sendRaw", f"KICK {ch} {nick} :{reason}"), ("sendCommand", f"KICK {ch} {nick} :{reason}")):
                    fn = getattr(self.bridge, meth, None)
                    if callable(fn):
                        try:
                            fn(ch, nick, reason) if cmd is None else fn(cmd)
                            sent = True
                            break
                        except Exception:
                            pass
                if not sent:
                    self.toast_host.show_toast("Kick not implemented in bridge")
        elif action == "ban":
            ch = self.bridge.current_channel() or ""
            mask, ok = QInputDialog.getText(self, "Ban", f"Ban mask or nick for {ch} (e.g. {nick} or *!*@host):", text=nick)
            if ok and mask.strip():
                sent = False
                for meth, cmd in (("setModes", None), ("sendRaw", f"MODE {ch} +b {mask}"), ("sendCommand", f"MODE {ch} +b {mask}")):
                    fn = getattr(self.bridge, meth, None)
                    if callable(fn):
                        try:
                            fn(ch, "+b " + mask) if cmd is None else fn(cmd)
                            sent = True
                            break
                        except Exception:
                            pass
                if not sent:
                    self.toast_host.show_toast("Ban not implemented in bridge")
        elif action == "op":
            ch = self.bridge.current_channel() or ""
            sent = False
            for meth, cmd in (("setModes", None), ("sendRaw", f"MODE {ch} +o {nick}"), ("sendCommand", f"MODE {ch} +o {nick}")):
                fn = getattr(self.bridge, meth, None)
                if callable(fn):
                    try:
                        fn(ch, "+o " + nick) if cmd is None else fn(cmd)
                        sent = True
                        break
                    except Exception:
                        pass
            if not sent:
                self.toast_host.show_toast("Op not implemented in bridge")
        elif action == "deop":
            ch = self.bridge.current_channel() or ""
            sent = False
            for meth, cmd in (("setModes", None), ("sendRaw", f"MODE {ch} -o {nick}"), ("sendCommand", f"MODE {ch} -o {nick}")):
                fn = getattr(self.bridge, meth, None)
                if callable(fn):
                    try:
                        fn(ch, "-o " + nick) if cmd is None else fn(cmd)
                        sent = True
                        break
                    except Exception:
                        pass
            if not sent:
                self.toast_host.show_toast("Deop not implemented in bridge")
        elif action == "add friend":
            # Add to friends list and persist
            try:
                current = [self.friends.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.friends.list.count())]
                if nick not in current:
                    current.append(nick)
                    self.friends.set_friends(current)
                    self.bridge.setMonitorList(current)
                    try:
                        s = QSettings("Peach", "PeachClient")
                        s.setValue("friends", current)
                    except Exception:
                        pass
                self.toast_host.show_toast(f"Added {nick} to friends")
            except Exception:
                pass
        else:
            self.toast_host.show_toast(f"Action '{action}' for {nick} not yet implemented")

    # ----- Find in buffer -----
    def _on_find(self, pattern: str, forward: bool) -> None:
        if not pattern:
            return
        flags = QTextDocument.FindFlag(0) if forward else QTextDocument.FindFlag.FindBackward
        try:
            self.chat.find(pattern, flags)
        except Exception:
            # Fallback: simple contains -> move cursor to end/start
            c = self.chat.textCursor()
            if forward:
                c.movePosition(c.MoveOperation.End)
            else:
                c.movePosition(c.MoveOperation.Start)
            self.chat.setTextCursor(c)

    def _open_find_panel(self) -> None:
        try:
            self.find_dock.show()
            self.find_dock.raise_()
            # focus the input
            try:
                self.find_bar.edit.setFocus()
                self.find_bar.edit.selectAll()
            except Exception:
                pass
        except Exception:
            pass

    # ----- Utilities -----
    def _strip_irc_codes(self, s: str) -> str:
        """Remove IRC control codes (color/bold/underline/reverse/reset) and CTCP wrappers."""
        if not s:
            return s
        try:
            # Strip CTCP \x01 wrappers
            if s.startswith("\x01") and s.endswith("\x01"):
                s = s.strip("\x01")
            # mIRC color code: \x03([0-9]{1,2})(,[0-9]{1,2})?
            s = re.sub(r"\x03(\d{1,2})(,\d{1,2})?", "", s)
            # Remove formatting control chars: bold(\x02), italic(\x1D), underline(\x1F), reverse(\x16), reset(\x0F)
            s = s.replace("\x02", "").replace("\x1D", "").replace("\x1F", "").replace("\x16", "").replace("\x0F", "")
            return s
        except Exception:
            return s

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        # File
        file_menu = menubar.addMenu("&File")
        act_open_logs = QAction("Open Logs Folder", self)
        act_open_logs.setIcon(get_icon(["logs", "folder", "folder-open"], awesome_fallback="fa5s.folder-open"))
        act_open_logs.triggered.connect(self._open_logs_folder)
        file_menu.addAction(act_open_logs)
        file_menu.addSeparator()
        act_exit = QAction("E&xit", self)
        act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        act_exit.setIcon(get_icon(["exit", "quit", "power"], awesome_fallback="fa5s.power-off"))
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # View
        view_menu = menubar.addMenu("&View")

        # Appearance (themes, fonts, transparency, radius)
        appearance_menu = view_menu.addMenu("Appearance")
        # Theme actions with two-way sync
        from PyQt6.QtGui import QActionGroup
        self._theme_actions: dict[str, QAction] = {}
        self._theme_group = QActionGroup(self)
        self._theme_group.setExclusive(True)
        if _theme_manager is not None:
            act_tm_dark = QAction("Material Dark", self, checkable=True)
            act_tm_light = QAction("Material Light", self, checkable=True)
            act_tm_dark.triggered.connect(lambda: self._apply_theme("Material Dark"))
            act_tm_light.triggered.connect(lambda: self._apply_theme("Material Light"))
            self._theme_group.addAction(act_tm_dark)
            self._theme_group.addAction(act_tm_light)
            appearance_menu.addActions([act_tm_dark, act_tm_light])
            self._theme_actions["Material Dark"] = act_tm_dark
            self._theme_actions["Material Light"] = act_tm_light
        try:
            import qt_material  # noqa: F401
            qtmat_menu = appearance_menu.addMenu("Qt Material Presets")
            presets = (
                "indigo_dark", "indigo_light",
                "teal_dark", "teal_light",
                "cyan_dark", "cyan_light",
                "blue_dark", "blue_light",
                "purple_dark", "purple_light",
                "deep_purple_dark", "deep_purple_light",
                "amber_dark", "amber_light",
                "red_dark", "red_light",
            )
            for name in presets:
                title = name.replace("_", " ").title()
                a = QAction(title, self, checkable=True)
                a.triggered.connect(lambda _, n=name: self._apply_qt_material(n))
                self._theme_group.addAction(a)
                qtmat_menu.addAction(a)
                self._theme_actions[name] = a
        except Exception:
            pass
        act_font = QAction("Choose Font…", self)
        act_font.triggered.connect(self._choose_font)
        appearance_menu.addAction(act_font)
        transp_menu = appearance_menu.addMenu("Transparency")
        for pct in (100, 95, 90, 85, 80):
            a = QAction(f"{pct}%", self)
            a.triggered.connect(lambda _, p=pct: self.setWindowOpacity(p/100.0))
            transp_menu.addAction(a)
        radius_menu = appearance_menu.addMenu("Corner Radius")
        for r in (0, 4, 8, 12, 16):
            a = QAction(f"{r}px", self)
            a.triggered.connect(lambda _, rv=r: self._set_corner_radius(rv))
            radius_menu.addAction(a)

        # Panels (toggle docks)
        panels_menu = view_menu.addMenu("Panels")
        # Built-in toggle actions from docks
        a_log = self.log_dock.toggleViewAction()
        a_log.setShortcut(QKeySequence("Ctrl+L"))
        a_urls = self.url_dock.toggleViewAction()
        a_urls.setShortcut(QKeySequence("Ctrl+U"))
        a_friends = self.friends_dock.toggleViewAction()
        a_friends.setShortcut(QKeySequence("Ctrl+Shift+F"))
        panels_menu.addActions([a_log, a_urls, a_friends])
        # Find panel opener (focuses search)
        act_find = QAction("Find…", self)
        act_find.setShortcut(QKeySequence.StandardKey.Find)
        act_find.setIcon(get_icon(["find", "search"], awesome_fallback="fa5s.search"))
        act_find.triggered.connect(self._open_find_panel)
        panels_menu.addAction(act_find)
        # Browser panel toggle (lazy create)
        act_browser_panel = QAction("Browser", self)
        act_browser_panel.setIcon(get_icon(["browser", "globe", "web"], awesome_fallback="fa5s.globe"))
        act_browser_panel.setShortcut(QKeySequence("Ctrl+B"))
        act_browser_panel.triggered.connect(self._toggle_browser_panel)
        panels_menu.addAction(act_browser_panel)

        # Word wrap and timestamps toggles in Appearance
        self.act_wrap = QAction("Word Wrap", self, checkable=True)
        self.act_wrap.toggled.connect(self._set_word_wrap)
        appearance_menu.addAction(self.act_wrap)
        self.act_timestamps = QAction("Show Timestamps", self, checkable=True)
        self.act_timestamps.toggled.connect(self._set_timestamps)
        appearance_menu.addAction(self.act_timestamps)

        # Tools
        tools_menu = menubar.addMenu("&Tools")
        act_plugins = QAction("Plugins…", self)
        act_plugins.setIcon(get_icon(["plugins", "puzzle"], awesome_fallback="fa5s.puzzle-piece"))
        act_plugins.triggered.connect(self._open_plugins_folder)
        tools_menu.addAction(act_plugins)
        # Internal Browser panel
        act_reset_profile = QAction("Reset Browser Profile…", self)
        act_reset_profile.setIcon(get_icon(["reset", "refresh", "broom"], awesome_fallback="fa5s.trash"))
        act_reset_profile.triggered.connect(self._reset_browser_profile)
        tools_menu.addAction(act_reset_profile)
        act_browser = QAction("Browser Panel", self)
        act_browser.setIcon(get_icon(["browser", "globe", "earth"], awesome_fallback="fa5s.globe"))
        act_browser.triggered.connect(self._toggle_browser_panel)
        tools_menu.addAction(act_browser)
        # Import cookies for current site
        act_cookies = QAction("Import Cookies for Site", self)
        act_cookies.setIcon(get_icon(["cookie", "cookies"], awesome_fallback="fa5s.cookie-bite"))
        act_cookies.triggered.connect(self._import_system_cookies_for_current_site)
        tools_menu.addAction(act_cookies)
        # Settings dialog
        act_settings = QAction("Settings…", self)
        act_settings.setIcon(get_icon(["settings", "cog", "gear"], awesome_fallback="fa5s.cog"))
        act_settings.triggered.connect(self._open_settings_dialog)
        tools_menu.addAction(act_settings)
        # Toggle Browser dock from Tools
        act_browser_tools = QAction("Toggle Browser Panel", self)
        act_browser_tools.setIcon(get_icon(["browser", "globe", "web"], awesome_fallback="fa5s.globe"))
        act_browser_tools.setShortcut(QKeySequence("Ctrl+B"))
        act_browser_tools.triggered.connect(self._toggle_browser_panel)
        tools_menu.addAction(act_browser_tools)
        # Import cookies from system browsers for current site (keep under Tools)
        act_import_cookies = QAction("Import System Cookies…", self)
        act_import_cookies.setIcon(get_icon(["cookies", "cookie"], awesome_fallback="fa5s.cookie-bite"))
        act_import_cookies.triggered.connect(self._import_system_cookies_for_current_site)
        tools_menu.addAction(act_import_cookies)
        # AI submenu under Tools
        ai_menu = tools_menu.addMenu("AI")
        act_ai_start = QAction("Start AI Chat…", self)
        act_ai_start.setIcon(get_icon(["ai", "robot"], awesome_fallback="mdi6.robot"))
        act_ai_start.triggered.connect(self._start_ai_chat)
        ai_menu.addAction(act_ai_start)
        act_ai_route = QAction("Route AI Output…", self)
        act_ai_route.setIcon(get_icon(["route", "arrow-right", "ai"], awesome_fallback="fa5s.location-arrow"))
        act_ai_route.triggered.connect(self._choose_ai_route_target)
        ai_menu.addAction(act_ai_route)
        self.act_ai_route_stop = QAction("Stop AI Output Routing", self)
        self.act_ai_route_stop.setIcon(get_icon(["stop", "square"], awesome_fallback="fa5s.stop"))
        self.act_ai_route_stop.triggered.connect(self._stop_ai_route)
        self.act_ai_route_stop.setEnabled(False)
        ai_menu.addAction(self.act_ai_route_stop)

        # Chat submenu under Tools
        chat_menu = tools_menu.addMenu("Chat")
        # Global shortcuts
        act_clear = QAction("Clear Buffer", self)
        act_clear.setShortcut(QKeySequence("Ctrl+K"))
        act_clear.setIcon(get_icon(["clear", "broom", "eraser"], awesome_fallback="fa5s.eraser"))
        act_clear.triggered.connect(self._clear_buffer)
        self.addAction(act_clear)
        chat_menu.addAction(act_clear)
        act_close = QAction("Close Current Channel", self)
        act_close.setShortcut(QKeySequence("Ctrl+W"))
        act_close.setIcon(get_icon(["close", "times", "x"], awesome_fallback="fa5s.times"))
        act_close.triggered.connect(self._close_current_channel)
        self.addAction(act_close)
        chat_menu.addAction(act_close)

        # Servers menu (manage saved servers)
        servers_menu = menubar.addMenu("&Servers")
        act_srv_panel = QAction("Servers Panel", self)
        act_srv_panel.triggered.connect(self._toggle_servers_panel)
        servers_menu.addAction(act_srv_panel)
        servers_menu.addSeparator()
        act_srv_connect = QAction("Connect to…", self)
        act_srv_connect.triggered.connect(self._servers_connect)
        servers_menu.addAction(act_srv_connect)
        servers_menu.addSeparator()
        act_srv_add = QAction("Add Server…", self)
        act_srv_add.triggered.connect(self._servers_add)
        act_srv_edit = QAction("Edit Server…", self)
        act_srv_edit.triggered.connect(self._servers_edit)
        act_srv_del = QAction("Delete Server…", self)
        act_srv_del.triggered.connect(self._servers_delete_prompt)
        servers_menu.addActions([act_srv_add, act_srv_edit, act_srv_del])
        servers_menu.addSeparator()
        act_srv_auto = QAction("Set Auto-connect…", self)
        act_srv_auto.triggered.connect(self._servers_set_autoconnect)
        servers_menu.addAction(act_srv_auto)
        act_srv_tls_ignore = QAction("Set Ignore Invalid Certs…", self)
        act_srv_tls_ignore.triggered.connect(self._servers_set_ignore_invalid_certs)
        servers_menu.addAction(act_srv_tls_ignore)

        # Help
        help_menu = menubar.addMenu("&Help")
        act_about = QAction("About", self)
        act_about.setIcon(get_icon(["about", "info"], awesome_fallback="fa5s.info-circle"))
        act_about.triggered.connect(lambda: self.toast_host.show_toast("Peach PyQt6 UI"))
        help_menu.addAction(act_about)

        # Notifications submenu under Tools (merged)
        notif_menu = tools_menu.addMenu("Notifications")
        act_toggle_sound = QAction("Enable Sound", self, checkable=True)
        act_toggle_sound.setChecked(True)
        act_toggle_sound.setIcon(get_icon(["sound", "bell"], awesome_fallback="fa5s.bell"))
        act_toggle_sound.toggled.connect(self._set_sound_enabled)
        notif_menu.addAction(act_toggle_sound)
        act_highlight_words = QAction("Set Highlight Words…", self)
        act_highlight_words.setIcon(get_icon(["highlight", "marker", "edit"], awesome_fallback="fa5s.highlighter"))
        act_highlight_words.triggered.connect(self._edit_highlight_words)
        notif_menu.addAction(act_highlight_words)
        act_notif_cfg = QAction("Configure…", self)
        act_notif_cfg.setIcon(get_icon(["notifications", "bell", "settings"], awesome_fallback="fa5s.cog"))
        act_notif_cfg.triggered.connect(self._open_notifications_settings)
        notif_menu.addAction(act_notif_cfg)

    

    def _toggle_browser_panel(self) -> None:
        self._ensure_browser_dock()
        if not self.browser_dock:
            return
        vis = not self.browser_dock.isVisible()
        self.browser_dock.setVisible(vis)
        if vis:
            self.browser_dock.raise_()
            self.browser_dock.activateWindow()

    def _open_plugins_folder(self) -> None:
        try:
            base = Path(__file__).resolve().parents[2] / "plugins"
            base.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(base)))
        except Exception as e:
            self.toast_host.show_toast(f"Open plugins folder failed: {e}")

    def _open_notifications_settings(self) -> None:
        # Simple dialog with checkboxes persisted to QSettings
        dlg = QDialog(self)
        dlg.setWindowTitle("Notification Settings")
        lay = QVBoxLayout(dlg)
        cb_pm = QCheckBox("Notify on private messages (PM)")
        cb_mention = QCheckBox("Notify on @mentions (your nick)")
        cb_hl = QCheckBox("Notify on highlight words")
        cb_joinpart = QCheckBox("Notify on joins/parts")
        # Load from settings
        try:
            s = QSettings("Peach", "PeachClient")
            cb_pm.setChecked(s.value("notifications/pm", self._notify_on_pm, type=bool))
            cb_mention.setChecked(s.value("notifications/mention", self._notify_on_mention, type=bool))
            cb_hl.setChecked(s.value("notifications/highlight", self._notify_on_highlight, type=bool))
            cb_joinpart.setChecked(s.value("notifications/join_part", self._notify_on_join_part, type=bool))
        except Exception:
            cb_pm.setChecked(self._notify_on_pm)
            cb_mention.setChecked(self._notify_on_mention)
            cb_hl.setChecked(self._notify_on_highlight)
            cb_joinpart.setChecked(self._notify_on_join_part)
        for cb in (cb_pm, cb_mention, cb_hl, cb_joinpart):
            lay.addWidget(cb)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        lay.addWidget(btns)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self._notify_on_pm = cb_pm.isChecked()
            self._notify_on_mention = cb_mention.isChecked()
            self._notify_on_highlight = cb_hl.isChecked()
            self._notify_on_join_part = cb_joinpart.isChecked()
            try:
                s = QSettings("Peach", "PeachClient")
                s.setValue("notifications/pm", self._notify_on_pm)
                s.setValue("notifications/mention", self._notify_on_mention)
                s.setValue("notifications/highlight", self._notify_on_highlight)
                s.setValue("notifications/join_part", self._notify_on_join_part)
            except Exception:
                pass

    # ----- Servers dock -----
    def _ensure_servers_dock(self) -> None:
        if getattr(self, 'servers_dock', None) is None:
            try:
                dock = QDockWidget("Servers", self)
                dock.setObjectName("ServersDock")
                # Build contents
                container = QWidget(dock)
                v = QVBoxLayout(container)
                v.setContentsMargins(6, 6, 6, 6)
                lst = QListWidget(container)
                self.servers_list_widget = lst
                v.addWidget(lst)
                # Buttons row
                row = QHBoxLayout()
                btn_connect = QPushButton("Connect", container)
                btn_add = QPushButton("Add", container)
                btn_edit = QPushButton("Edit", container)
                btn_del = QPushButton("Delete", container)
                btn_auto = QPushButton("Set Auto", container)
                btn_ignore = QPushButton("Toggle Ignore Certs", container)
                for b in (btn_connect, btn_add, btn_edit, btn_del, btn_auto, btn_ignore):
                    row.addWidget(b)
                v.addLayout(row)
                container.setLayout(v)
                dock.setWidget(container)
                self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
                self.servers_dock = dock
                # Disallow floating
                try:
                    feats = dock.features()
                    from PyQt6.QtWidgets import QDockWidget as _QDock
                    dock.setFeatures(feats & ~_QDock.DockWidgetFeature.DockWidgetFloatable)
                except Exception:
                    pass
                # Wire buttons
                btn_connect.clicked.connect(self._servers_panel_connect)
                btn_add.clicked.connect(self._servers_add)
                btn_edit.clicked.connect(self._servers_panel_edit)
                btn_del.clicked.connect(self._servers_panel_delete)
                btn_auto.clicked.connect(self._servers_panel_set_auto)
                btn_ignore.clicked.connect(self._servers_panel_toggle_ignore)
                # Populate
                self._refresh_servers_list()
                dock.hide()
            except Exception:
                self.servers_dock = None

    def _refresh_servers_list(self) -> None:
        try:
            if not hasattr(self, 'servers_list_widget'):
                return
            lst = self.servers_list_widget
            lst.clear()
            for name in self._servers_list():
                lst.addItem(name)
        except Exception:
            pass

    def _selected_server_name(self) -> str | None:
        try:
            lst = getattr(self, 'servers_list_widget', None)
            if not lst:
                return None
            it = lst.currentItem()
            return it.text() if it else None
        except Exception:
            return None

    def _toggle_servers_panel(self) -> None:
        self._ensure_servers_dock()
        if not self.servers_dock:
            return
        if self.servers_dock.isVisible():
            self.servers_dock.hide()
        else:
            self._refresh_servers_list()
            self.servers_dock.show()
            try:
                self.servers_dock.raise_()
            except Exception:
                pass

    # Panel actions operating on selection
    def _servers_panel_connect(self) -> None:
        name = self._selected_server_name()
        if not name:
            return
        self._servers_connect_name(name)

    def _servers_panel_edit(self) -> None:
        name = self._selected_server_name()
        if not name:
            return
        self._servers_edit_name(name)
        self._refresh_servers_list()

    def _servers_panel_delete(self) -> None:
        name = self._selected_server_name()
        if not name:
            return
        self._servers_delete_name(name)
        self._refresh_servers_list()

    def _servers_panel_set_auto(self) -> None:
        name = self._selected_server_name()
        if not name:
            return
        self._servers_set_autoconnect_name(name)
        self.status.showMessage(f"Auto-connect set to {name}", 1500)

    def _servers_panel_toggle_ignore(self) -> None:
        name = self._selected_server_name()
        if not name:
            return
        self._servers_toggle_ignore_name(name)

    # Helpers acting by name (no dialogs)
    def _servers_connect_name(self, name: str) -> None:
        data = self._servers_load(name)
        if not data:
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, _auto, ignore = data
        # Record current saved server name for persistence of channels
        self._current_server_name = name
        host = self._normalize_host(host)
        host, port, tls = self._resolve_connect_policy(host, port, tls)
        if tls:
            self._apply_tls_ignore_setting(ignore)
        try:
            # track last TLS choice
            self._last_connect_tls = bool(tls)
            self._schedule_async(self.bridge.connectHost, host, port, tls, nick, user, realname, chans, password, sasl_user, bool(ignore))
            if getattr(self, "_auto_negotiate", True):
                self._schedule_async(self._negotiate_on_connect, host, nick, user, password, sasl_user)
            self.status.showMessage(f"Connecting to {host}:{port}…", 2000)
            self._my_nick = nick
        except Exception:
            try:
                self.bridge.connectHost(host, port, tls, nick, user, realname, chans, password, sasl_user, bool(ignore))
                if getattr(self, "_auto_negotiate", True):
                    self._schedule_async(self._negotiate_on_connect, host, nick, user, password, sasl_user)
            except Exception:
                pass

    def _servers_edit_name(self, name: str) -> None:
        data = self._servers_load(name)
        if not data:
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, autoconnect, ignore = data
        dlg = ConnectDialog(self)
        try:
            dlg.set_values(host, port, tls, nick, user, realname, chans, password, sasl_user, True, autoconnect)
        except Exception:
            pass
        if dlg.exec() == dlg.DialogCode.Accepted:
            vals = dlg.values()
            host, port, tls, nick, user, realname, chans, password, sasl_user, remember, autoconnect = vals
            self._servers_save(name, host, port, tls, nick, user, realname, chans, bool(autoconnect), password, sasl_user, ignore)

    def _servers_toggle_ignore_name(self, name: str) -> None:
        data = self._servers_load(name)
        if not data:
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, autoconnect, ignore = data
        self._servers_save(name, host, port, tls, nick, user, realname, chans, bool(autoconnect), password, sasl_user, not ignore)
        self.status.showMessage(f"Ignore invalid certs: {'Yes' if not ignore else 'No'} for {name}", 1500)

    def _show_browser_panel(self) -> None:
        self._ensure_browser_dock()
        if not self.browser_dock:
            return
        self.browser_dock.show()
        try:
            self.browser_dock.raise_()
        except Exception:
            pass

    def _import_system_cookies_for_current_site(self) -> None:
        try:
            self._ensure_browser_dock()
            if not self.browser_dock:
                self.toast_host.show_toast("Browser panel unavailable")
                return
            url = self.browser_dock.view.url()
            host = url.host()
            if not host:
                self.toast_host.show_toast("Open a site in the Browser first")
                return
            # Import cookies for this domain
            n = self.browser_dock.import_cookies_from_system(domain=host)
            if n > 0:
                self.status.showMessage(f"Imported {n} cookies for {host}", 2500)
                # Reload to apply
                self.browser_dock.view.reload()
            else:
                self.toast_host.show_toast("No cookies imported (install browser-cookie3?)")
        except Exception:
            self.toast_host.show_toast("Cookie import failed")

    def _ensure_browser_dock(self) -> None:
        if self.browser_dock is None:
            try:
                # Lazy import to avoid circular import with browser_dock -> main_window
                from .widgets.browser_dock import BrowserDock
                bd = BrowserDock(self)
                self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, bd)
                bd.hide()
                self.browser_dock = bd
            except Exception:
                self.browser_dock = None
        # Force docked state if it exists
        try:
            if self.browser_dock and hasattr(self.browser_dock, "setFloating"):
                self.browser_dock.setFloating(False)
            # Disallow floating to avoid separate window popping
            if self.browser_dock:
                feats = self.browser_dock.features()
                from PyQt6.QtWidgets import QDockWidget
                self.browser_dock.setFeatures(feats & ~QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        except Exception:
            pass

    def _reset_browser_profile(self) -> None:
        """Delete the persistent internal browser profile and reset the dock.

        Closes and destroys the current browser dock (if any), removes the
        profile directory at app/resources/qtweb/browser, and defers
        re-creation until the browser panel is next requested.
        """
        # 1) Close/hide and remove the dock safely
        try:
            if self.browser_dock is not None:
                try:
                    self.browser_dock.hide()
                except Exception:
                    pass
                try:
                    self.removeDockWidget(self.browser_dock)
                except Exception:
                    pass
                try:
                    self.browser_dock.deleteLater()
                except Exception:
                    pass
                self.browser_dock = None
        except Exception:
            pass
        # 2) Remove the persistent profile dir used by BrowserDock
        try:
            base = Path(__file__).resolve().parents[1] / "resources" / "qtweb" / "browser"
            # Best-effort removal (profile should be closed from step 1)
            shutil.rmtree(base, ignore_errors=True)
            # Recreate empty folder to avoid surprises on next launch
            try:
                base.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            self.status.showMessage("Browser profile reset", 2500)
            try:
                self.toast_host.show_toast("Browser profile reset. Open Browser panel to reinitialize.")
            except Exception:
                pass
        except Exception:
            try:
                self.toast_host.show_toast("Failed to reset browser profile")
            except Exception:
                pass

    def _show_browser_panel(self) -> None:
        self._ensure_browser_dock()
        if self.browser_dock:
            self.browser_dock.show()

    def _toggle_browser_panel(self) -> None:
        self._ensure_browser_dock()
        if not self.browser_dock:
            return
        if self.browser_dock.isVisible():
            self.browser_dock.hide()
        else:
            self.browser_dock.show()

    # ----- Formatting helpers -----
    _URL_RE = re.compile(r"(https?://\S+)")
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")

    def _youtube_id(self, url: str) -> str | None:
        try:
            if "youtu.be/" in url:
                return url.split("youtu.be/")[1].split("?")[0].split("&")[0]
            if "youtube.com" in url:
                if "v=" in url:
                    return url.split("v=")[1].split("&")[0]
                if "/shorts/" in url:
                    return url.split("/shorts/")[1].split("?")[0]
        except Exception:
            return None
        return None

    def _format_message_html(self, nick: str, text: str, ts: float | None = None) -> str:
        safe_text = text or ""
        m = self._URL_RE.search(safe_text)
        embed_html = ""
        if m:
            url = m.group(1)
            low = url.lower()
            if any(low.endswith(ext) for ext in self._IMG_EXTS):
                embed_html = f"<br><img src='{url}' style='max-width: 480px; border-radius: 6px;'>"
            else:
                yid = self._youtube_id(url)
                if yid:
                    thumb = f"https://img.youtube.com/vi/{yid}/hqdefault.jpg"
                    embed_html = f"<br><a href='{url}' target='_blank'><img src='{thumb}' style='max-width: 480px; border-radius: 6px;'><br>Open on YouTube</a>"
        prefix = ""
        if getattr(self, "_show_timestamps", False):
            if ts is None:
                ts = time.time()
            t = time.localtime(ts)
            prefix = f"<span style='color: #888'>[{t.tm_hour:02d}:{t.tm_min:02d}]</span> "
        return f"{prefix}<b>{nick}:</b> {safe_text}{embed_html}"

    def _on_submit(self, text: str) -> None:
        if not text.strip():
            return
        # Send via bridge
        cur = self.bridge.current_channel() or ""
        if cur.startswith("[AI:"):
            # AI session: stream response from Ollama
            self.chat.append(self._format_message_html("You", text, ts=time.time()))
            self._run_ai_inference(cur, text)
        else:
            if text.startswith('/'):
                self._handle_command(text, cur)
            else:
                try:
                    self.bridge.sendMessage(text)
                except Exception:
                    # Fallback: raw PRIVMSG to current target
                    if cur:
                        tgt = self._irc_target_from_label(cur)
                        if tgt:
                            self._send_raw(f"PRIVMSG {tgt} :{text}")
                # optionally local-echo your message for plain chat only
                try:
                    self.chat.append(self._format_message_html(self._my_nick or "You", text, ts=time.time()))
                except Exception:
                    pass

    def _handle_command(self, cmdline: str, cur: str) -> None:
        parts = cmdline.lstrip('/').split(' ', 1)
        cmd = (parts[0] if parts else '').lower()
        arg = parts[1] if len(parts) > 1 else ''
        def _raw(s: str) -> None:
            self._send_raw(s)
        def _send_to(target: str, msg: str) -> bool:
            fn = getattr(self.bridge, 'sendMessageTo', None)
            if callable(fn):
                try:
                    fn(target, msg)
                    return True
                except Exception:
                    pass
            return False
        if cmd in ("me",):
            # /me action
            action = arg.strip()
            if not action:
                return
            target = self._irc_target_from_label(cur) or cur
            if not target:
                return
            # CTCP ACTION
            if not _send_to(target, f"\x01ACTION {action}\x01"):
                _raw(f"PRIVMSG {target} :\x01ACTION {action}\x01")
            try:
                self.chat.append(self._format_message_html(self._my_nick or "You", f"* {action}", ts=time.time()))
            except Exception:
                pass
        elif cmd in ("join",):
            ch = arg.strip()
            if ch and not ch.startswith(('#', '&')):
                ch = '#' + ch
            if ch:
                try:
                    self.bridge.joinChannel(ch)
                except Exception:
                    _raw(f"JOIN {ch}")
                # Local echo of join
                try:
                    self.chat.append(f"<i>• Joined {ch}</i>")
                except Exception:
                    pass
        elif cmd in ("part", "leave"):
            ch = arg.strip() or cur
            if ch and not ch.startswith(('#', '&')):
                ch = '#' + ch
            if ch:
                try:
                    self.bridge.partChannel(ch)
                except Exception:
                    _raw(f"PART {ch}")
                # Local echo of part
                try:
                    self.chat.append(f"<i>• Left {ch}</i>")
                except Exception:
                    pass
        elif cmd == "nick":
            newn = arg.strip()
            if newn:
                try:
                    self.bridge.changeNick(newn)
                except Exception:
                    _raw(f"NICK {newn}")
                self._my_nick = newn
        elif cmd in ("msg", "query"):
            # /msg <target> <message>
            try:
                target, msg = arg.split(' ', 1)
            except ValueError:
                return
            target = target.strip()
            msg = msg.strip()
            if not target or not msg:
                return
            if not _send_to(target, msg):
                _raw(f"PRIVMSG {target} :{msg}")
            # Open PM channel label convention
            label = f"[PM:{target}]"
            try:
                if label not in self._channel_labels:
                    self._channel_labels.append(label)
                    self.sidebar.set_channels(self._channel_labels)
                    self.sidebar.set_unread(label, 0, 0)
                self.bridge.set_current_channel(label)
            except Exception:
                pass
        elif cmd == "whois":
            nick = arg.strip()
            if nick:
                _raw(f"WHOIS {nick}")
        elif cmd == "topic":
            # /topic [#chan] new topic
            if arg.startswith('#') and ' ' in arg:
                ch, topic = arg.split(' ', 1)
            else:
                ch, topic = cur, arg
            ch = (ch or '').strip()
            topic = (topic or '').strip()
            if ch and topic:
                try:
                    self.bridge.setTopic(ch, topic)
                except Exception:
                    _raw(f"TOPIC {ch} :{topic}")
        elif cmd == "mode":
            # /mode <target> <modes>
            try:
                target, modes = arg.split(' ', 1)
            except ValueError:
                return
            target = target.strip()
            modes = modes.strip()
            if not target or not modes:
                return
            try:
                self.bridge.setModes(target, modes)
            except Exception:
                _raw(f"MODE {target} {modes}")
        elif cmd == "raw":
            if arg:
                _raw(arg)
        else:
            # Unknown: try as raw
            if arg:
                _raw(parts[0].upper() + ' ' + arg)
            else:
                _raw(parts[0].upper())

    def _irc_target_from_label(self, label: str) -> str | None:
        """Derive an IRC target (channel or nick) from a UI label.

        Recognizes labels like:
        - "[PM:nick]" -> "nick"
        - composite labels containing a channel token starting with '#' -> that token
        - otherwise returns the label as-is
        """
        if not label:
            return None
        if label.startswith("[PM:") and label.endswith("]"):
            return label[4:-1]
        # Find a channel token
        for tok in re.split(r"\s+|,", label):
            if tok.startswith('#'):
                return tok
        return label

    def _send_raw(self, line: str) -> None:
        sent = False
        for meth in ("sendRaw", "sendCommand"):
            fn = getattr(self.bridge, meth, None)
            if callable(fn):
                try:
                    fn(line)
                    sent = True
                    break
                except Exception:
                    pass
        if not sent:
            self.toast_host.show_toast("Raw command not supported by bridge")

    def _on_status(self, s: str) -> None:
        # Feed negotiation parser first with raw line
        try:
            self._negotiate_handle_line(s or "")
        except Exception:
            pass
        # Minimal status verbosity: show only essential connection info
        clean = self._strip_irc_codes(s or "")
        txt = clean.strip()
        if not txt:
            return
        # Filter out raw protocol echoes and noisy lines
        if '>>' in txt:
            return
        # Drop lines that are only a bracketed network prefix like "[net]" or "[net]   "
        if txt.startswith('[') and ']' in txt and not txt.split(']', 1)[1].strip():
            return
        low = txt.lower()
        allowed = (
            ('connecting to ' in low) or
            ('connected. registering' in low) or
            ('registering (nick/user sent)' in low) or
            ('001 welcome received' in low)
        )
        if not allowed:
            return
        # Show allowed line in status bar and chat (italic)
        self.status.showMessage(clean, 2500)
        self.chat.append(f"<i>{clean}</i>")
        # auto-scroll chat
        try:
            c = self.chat.textCursor()
            c.movePosition(c.MoveOperation.End)
            self.chat.setTextCursor(c)
        except Exception:
            pass

    def _on_channel_action(self, ch: str, action: str) -> None:
        a = action.lower()
        if a == "open log":
            try:
                path = self.logger.path_for("irc", ch)
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
            except Exception as e:
                self.toast_host.show_toast(f"Open log failed: {e}")
        elif a == "join":
            try:
                self.bridge.joinChannel(ch)
            except Exception:
                self.toast_host.show_toast("Join not implemented in bridge")
        elif a == "part":
            try:
                self.bridge.partChannel(ch)
            except Exception:
                self.toast_host.show_toast("Part not implemented in bridge")
        elif a == "topic":
            dlg = TopicDialog(ch, None, self)
            if dlg.exec() == dlg.DialogCode.Accepted:
                new_topic = dlg.value()
                try:
                    self.bridge.setTopic(ch, new_topic)
                except Exception:
                    self.toast_host.show_toast("Topic change not implemented in bridge")
        elif a == "modes":
            dlg = ModesDialog(ch, self)
            if dlg.exec() == dlg.DialogCode.Accepted:
                modes = dlg.value()
                try:
                    self.bridge.setModes(ch, modes)
                except Exception:
                    self.toast_host.show_toast("Set modes not implemented in bridge")
        elif a == "close":
            # Simple close: part channel
            self._on_channel_action(ch, "Part")

    # ----- Settings management -----
    def _load_settings(self) -> None:
        s = QSettings("Peach", "PeachClient")
        self._current_theme = s.value("theme", type=str)
        self._word_wrap = s.value("word_wrap", True, type=bool)
        self._show_timestamps = s.value("show_timestamps", False, type=bool)
        self._chat_font_family = s.value("font_family", type=str)
        self._chat_font_size = s.value("font_size", type=int)
        # Network prefs
        self._auto_negotiate = s.value("network/auto_negotiate", True, type=bool)
        self._prefer_tls = s.value("network/prefer_tls", True, type=bool)
        self._try_starttls = s.value("network/try_starttls", False, type=bool)
        op = s.value("opacity", 1.0, type=float)
        try:
            self.setWindowOpacity(float(op))
        except Exception:
            pass
        # Restore geometry and splitter state
        try:
            geo: QByteArray | None = s.value("win_geometry", None, type=QByteArray)
            if geo:
                self.restoreGeometry(geo)
        except Exception:
            pass
        try:
            sp: QByteArray | None = s.value("split_lr_state", None, type=QByteArray)
            if sp and hasattr(self, "split_lr"):
                self.split_lr.restoreState(sp)
        except Exception:
            pass
        # Lists
        try:
            hl = s.value("highlight_words", [], type=list)
            self._highlight_keywords = list(hl)
        except Exception:
            pass
        try:
            friends = s.value("friends", [], type=list)
            if friends:
                self.friends.set_friends(list(friends))
                # push to bridge
                self.bridge.setMonitorList(list(friends))
        except Exception:
            pass

    def _save_settings(self) -> None:
        s = QSettings("Peach", "PeachClient")
        if self._current_theme:
            s.setValue("theme", self._current_theme)
        s.setValue("word_wrap", self._word_wrap)
        s.setValue("show_timestamps", self._show_timestamps)
        s.setValue("opacity", float(self.windowOpacity()))
        # Network prefs
        s.setValue("network/auto_negotiate", bool(getattr(self, "_auto_negotiate", True)))
        s.setValue("network/prefer_tls", bool(getattr(self, "_prefer_tls", True)))
        s.setValue("network/try_starttls", bool(getattr(self, "_try_starttls", False)))
        if self._chat_font_family:
            s.setValue("font_family", self._chat_font_family)
        if self._chat_font_size:
            s.setValue("font_size", int(self._chat_font_size))
        s.setValue("highlight_words", list(self._highlight_keywords))
        # friends from widget
        try:
            fr = [self.friends.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.friends.list.count())]
            s.setValue("friends", fr)
        except Exception:
            pass
        # Persist geometry and splitter state
        try:
            s.setValue("win_geometry", self.saveGeometry())
        except Exception:
            pass
        try:
            if hasattr(self, "split_lr"):
                s.setValue("split_lr_state", self.split_lr.saveState())
        except Exception:
            pass

    def closeEvent(self, ev) -> None:  # type: ignore[override]
        try:
            self._save_settings()
        finally:
            super().closeEvent(ev)

    def _apply_settings(self) -> None:
        # word wrap
        self._set_word_wrap(self._word_wrap)
        # timestamps
        self._set_timestamps(self._show_timestamps)
        # font
        if self._chat_font_family:
            f = self.chat.font()
            f.setFamily(self._chat_font_family)
            if self._chat_font_size and int(self._chat_font_size) > 0:
                f.setPointSize(int(self._chat_font_size))
            self.chat.setFont(f)
        # theme
        if self._current_theme:
            try:
                self._apply_qt_material(self._current_theme)
            except Exception:
                pass
        # sync theme menu checks
        try:
            self._sync_theme_actions()
        except Exception:
            pass

    def _open_settings_dialog(self) -> None:
        # Build theme options list
        theme_options: list[str] = []
        try:
            from qt_material import list_themes
            theme_options = list(list_themes()) or []
        except Exception:
            if _theme_manager is not None:
                theme_options = ["Material Dark", "Material Light"]
        from .dialogs.settings_dialog import SettingsDialog
        fam = self.chat.font().family()
        pt = self.chat.font().pointSize()
        # Guard against invalid point size (-1 when unset/pixel-based). Use a sane default.
        try:
            if pt is None or int(pt) <= 0:
                pt = 12
        except Exception:
            pt = 12
        # Load current autoconnect flag
        auto = False
        try:
            s = QSettings("Peach", "PeachClient")
            # Default to autoconnect enabled
            auto = s.value("server/autoconnect", True, type=bool)
        except Exception:
            pass
        dlg = SettingsDialog(self,
                         theme_options=theme_options,
                         current_theme=self._current_theme,
                         opacity=float(self.windowOpacity()),
                         font_family=fam,
                         font_point_size=pt,
                         highlight_words=self._highlight_keywords,
                         friends=[self.friends.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.friends.list.count())],
                         word_wrap=self._word_wrap,
                         show_timestamps=self._show_timestamps,
                         autoconnect=auto,
                         auto_negotiate=bool(getattr(self, "_auto_negotiate", True)),
                         prefer_tls=bool(getattr(self, "_prefer_tls", True)),
                         try_starttls=bool(getattr(self, "_try_starttls", False)))
        if dlg.exec() == dlg.DialogCode.Accepted:
            # Theme
            sel = dlg.selected_theme()
            if sel:
                self._current_theme = sel
                # Apply theme via qt-material if available; fallback to internal theme
                try:
                    self._apply_qt_material(sel)
                except Exception:
                    try:
                        self._apply_theme(sel)
                    except Exception:
                        pass
            # Opacity
            try:
                self.setWindowOpacity(dlg.selected_opacity())
            except Exception:
                pass
            # Font
            fam_sel, pt_sel = dlg.selected_font()
            if fam_sel:
                self._chat_font_family = fam_sel
            if pt_sel and pt_sel > 0:
                self._chat_font_size = pt_sel
            if fam_sel or (pt_sel and pt_sel > 0):
                f = self.chat.font()
                if fam_sel:
                    f.setFamily(fam_sel)
                if pt_sel and pt_sel > 0:
                    f.setPointSize(pt_sel)
                self.chat.setFont(f)
            # Word wrap, timestamps
            self._set_word_wrap(dlg.selected_word_wrap())
            self._set_timestamps(dlg.selected_show_timestamps())
            # Highlight words
            self._highlight_keywords = dlg.selected_highlight_words()
            # Friends
            fr = dlg.selected_friends()
            self.friends.set_friends(fr)
            self.bridge.setMonitorList(fr)
            # Network prefs
            try:
                self._auto_negotiate = dlg.selected_auto_negotiate()
                self._prefer_tls = dlg.selected_prefer_tls()
                # Optional STARTTLS attempt preference
                if hasattr(dlg, 'selected_try_starttls'):
                    self._try_starttls = dlg.selected_try_starttls()
            except Exception:
                pass
            # Persist
        try:
            # Save autoconnect flag only (server details saved via Connect dialog)
            s = QSettings("Peach", "PeachClient")
            s.setValue("server/autoconnect", dlg.selected_autoconnect())
        except Exception:
            pass
        self._save_settings()

    # ---- Server persistence / autoconnect ----
    def _save_server_settings(self, host: str, port: int, tls: bool, nick: str, user: str, realname: str,
                               channels: list[str], autoconnect: bool, password: str | None, sasl_user: str | None) -> None:
        try:
            s = QSettings("Peach", "PeachClient")
            s.setValue("server/host", host)
            s.setValue("server/port", int(port))
            s.setValue("server/tls", bool(tls))
            s.setValue("server/nick", nick)
            s.setValue("server/user", user)
            s.setValue("server/realname", realname)
            s.setValue("server/channels", channels)
            s.setValue("server/autoconnect", bool(autoconnect))
            # Optionally persist credentials (basic, not encrypted)
            if password:
                s.setValue("server/password", password)
            if sasl_user:
                s.setValue("server/sasl_user", sasl_user)
        except Exception:
            pass

    def _load_server_settings(self) -> tuple | None:
        try:
            s = QSettings("Peach", "PeachClient")
            # Defaults point to debauchedtea.party:1337 (TLS enabled)
            host = s.value("server/host", "debauchedtea.party", type=str)
            port = s.value("server/port", 1337, type=int)
            tls = s.value("server/tls", True, type=bool)
            nick = s.value("server/nick", "peach", type=str)
            user = s.value("server/user", type=str)
            realname = s.value("server/realname", type=str)
            channels = s.value("server/channels", [], type=list) or []
            password = s.value("server/password", None, type=str)
            sasl_user = s.value("server/sasl_user", None, type=str)
            # Default autoconnect enabled
            autoconnect = s.value("server/autoconnect", True, type=bool)
            if host and nick:
                return host, int(port), bool(tls), nick, user or "peach", realname or "Peach Client", list(channels), password, sasl_user, bool(autoconnect)
        except Exception:
            pass
        return None

    def _maybe_autoconnect_from_settings(self) -> None:
        # Prefer new multi-server store
        srv = self._servers_get_autoconnect()
        if srv:
            host, port, tls, nick, user, realname, channels, password, sasl_user, ignore = srv
        else:
            data = self._load_server_settings()
            if not data:
                return
            host, port, tls, nick, user, realname, channels, password, sasl_user, autoconnect = data
            if not autoconnect:
                return
            ignore = False
        # Sanitize hostname
        host = self._normalize_host(host)
        # Apply connection policy
        host, port, tls = self._resolve_connect_policy(host, port, tls)
        # Apply TLS cert verify policy if possible
        if tls:
            self._apply_tls_ignore_setting(ignore)
        try:
            self._schedule_async(self.bridge.connectHost, host, port, tls, nick, user, realname, channels, password, sasl_user, bool(ignore))
            if getattr(self, "_auto_negotiate", True):
                # Best-effort: kick off negotiation shortly after connect
                self._schedule_async(self._negotiate_on_connect, host, nick, user, password, sasl_user)
            self.status.showMessage(f"Auto-connecting to {host}:{port}…", 2000)
            self._my_nick = nick
        except Exception:
            try:
                self.bridge.connectHost(host, port, tls, nick, user, realname, channels, password, sasl_user, bool(ignore))
                if getattr(self, "_auto_negotiate", True):
                    self._schedule_async(self._negotiate_on_connect, host, nick, user, password, sasl_user)
            except Exception:
                pass

    def _set_word_wrap(self, en: bool) -> None:
        self._word_wrap = bool(en)
        self.chat.setLineWrapMode(
            QTextEdit.LineWrapMode.WidgetWidth if self._word_wrap else QTextEdit.LineWrapMode.NoWrap
        )
        try:
            self.act_wrap.setChecked(self._word_wrap)
        except Exception:
            pass

    def _set_timestamps(self, en: bool) -> None:
        self._show_timestamps = bool(en)
        try:
            self.act_timestamps.setChecked(self._show_timestamps)
        except Exception:
            pass

    # ----- QoL actions -----
    def _clear_buffer(self) -> None:
        self.chat.clear()

    def _close_current_channel(self) -> None:
        cur = self.bridge.current_channel() or ""
        if not cur:
            return
        if cur.startswith("[AI:"):
            # Remove AI pseudo-channel
            try:
                if cur in self._channel_labels:
                    self._channel_labels.remove(cur)
                    self.sidebar.set_channels(self._channel_labels)
            except Exception:
                pass
            # switch to any remaining channel
            if self._channel_labels:
                self.bridge.set_current_channel(self._channel_labels[0])
            else:
                self.bridge.set_current_channel("")
        else:
            # IRC part
            try:
                self.bridge.partChannel(cur)
            except Exception:
                pass

    def _open_logs_folder(self) -> None:
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.logger.base)))
        except Exception as e:
            self.toast_host.show_toast(f"Open folder failed: {e}")

    # ----- Member actions -----
    def _on_member_action(self, nick: str, action: str) -> None:
        action = action.lower()
        if action == "whois":
            # Try to send raw WHOIS if bridge supports it
            sent = False
            for meth in ("sendRaw", "sendCommand"):
                fn = getattr(self.bridge, meth, None)
                if callable(fn):
                    try:
                        fn(f"WHOIS {nick}")
                        sent = True
                        break
                    except Exception:
                        pass
            if not sent:
                self.chat.append(f"<i>WHOIS {nick} (not sent: no raw command API)</i>")
        elif action == "query":
            label = f"[PM:{nick}]"
            try:
                self.sidebar.set_channels([label])
                self.sidebar.set_unread(label, 0, 0)
            except Exception:
                pass
            self.bridge.set_current_channel(label)
        elif action == "kick":
            ch = self.bridge.current_channel() or ""
            reason, ok = QInputDialog.getText(self, "Kick", f"Reason for kicking {nick} from {ch}:", text="")
            if ok:
                sent = False
                for meth, cmd in (("kickUser", None), ("sendRaw", f"KICK {ch} {nick} :{reason}"), ("sendCommand", f"KICK {ch} {nick} :{reason}")):
                    fn = getattr(self.bridge, meth, None)
                    if callable(fn):
                        try:
                            fn(ch, nick, reason) if cmd is None else fn(cmd)
                            sent = True
                            break
                        except Exception:
                            pass
                if not sent:
                    self.toast_host.show_toast("Kick not implemented in bridge")
        elif action == "ban":
            ch = self.bridge.current_channel() or ""
            mask, ok = QInputDialog.getText(self, "Ban", f"Ban mask or nick for {ch} (e.g. {nick} or *!*@host):", text=nick)
            if ok and mask.strip():
                sent = False
                for meth, cmd in (("setModes", None), ("sendRaw", f"MODE {ch} +b {mask}"), ("sendCommand", f"MODE {ch} +b {mask}")):
                    fn = getattr(self.bridge, meth, None)
                    if callable(fn):
                        try:
                            fn(ch, "+b " + mask) if cmd is None else fn(cmd)
                            sent = True
                            break
                        except Exception:
                            pass
                if not sent:
                    self.toast_host.show_toast("Ban not implemented in bridge")
        elif action == "op":
            ch = self.bridge.current_channel() or ""
            sent = False
            for meth, cmd in (("setModes", None), ("sendRaw", f"MODE {ch} +o {nick}"), ("sendCommand", f"MODE {ch} +o {nick}")):
                fn = getattr(self.bridge, meth, None)
                if callable(fn):
                    try:
                        fn(ch, "+o " + nick) if cmd is None else fn(cmd)
                        sent = True
                        break
                    except Exception:
                        pass
            if not sent:
                self.toast_host.show_toast("Op not implemented in bridge")
        elif action == "deop":
            ch = self.bridge.current_channel() or ""
            sent = False
            for meth, cmd in (("setModes", None), ("sendRaw", f"MODE {ch} -o {nick}"), ("sendCommand", f"MODE {ch} -o {nick}")):
                fn = getattr(self.bridge, meth, None)
                if callable(fn):
                    try:
                        fn(ch, "-o " + nick) if cmd is None else fn(cmd)
                        sent = True
                        break
                    except Exception:
                        pass
            if not sent:
                self.toast_host.show_toast("Deop not implemented in bridge")
        else:
            self.toast_host.show_toast(f"Action '{action}' for {nick} not yet implemented")

    # ----- Find in buffer -----
    def _on_find(self, pattern: str, forward: bool) -> None:
        if not pattern:
            return
        flags = QTextDocument.FindFlag(0) if forward else QTextDocument.FindFlag.FindBackward
        try:
            self.chat.find(pattern, flags)
        except Exception:
            # Fallback: simple contains -> move cursor to end/start
            c = self.chat.textCursor()
            if forward:
                c.movePosition(c.MoveOperation.End)
            else:
                c.movePosition(c.MoveOperation.Start)
            self.chat.setTextCursor(c)

    # ----- Theme helpers -----
    def _apply_theme(self, name: str) -> None:
        if _theme_manager is None:
            return
        tm = _theme_manager()
        tm.set_theme(name)
        tm.apply()
        self._current_theme = name
        self._sync_theme_actions()

    def _apply_rounded_corners(self, radius_px: int = 8) -> None:
        """Append a minimal global stylesheet to enforce rounded corners consistently.

        Keep this lightweight to avoid fighting theme palettes. Safe to call repeatedly.
        """
        try:
            app = QApplication.instance()
            if not app:
                return
            r = max(0, int(radius_px))
            extra = (
                "\n"  # ensure separation
                "QPushButton, QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,\n"
                "QTextEdit, QPlainTextEdit, QListWidget, QTreeWidget, QTableWidget,\n"
                "QDockWidget, QMenu, QToolButton {\n"
                f"    border-radius: {r}px;\n"
                "}\n"
                "QTabBar::tab {\n"
                f"    border-top-left-radius: {r}px;\n"
                f"    border-top-right-radius: {r}px;\n"
                "}\n"
            )
            cur = app.styleSheet() or ""
            if extra.strip() not in cur:
                app.setStyleSheet(cur + extra)
        except Exception:
            pass

    def _apply_qt_material(self, theme: str) -> None:
        # Apply qt-material stylesheet if available; otherwise fallback to our theme manager
        try:
            from PyQt6.QtWidgets import QApplication
            from qt_material import apply_stylesheet, list_themes
            app = QApplication.instance()
            if app:
                themes = list_themes()
                chosen = theme
                if chosen not in themes:
                    candidates = []
                    base = (chosen or "").replace(".xml", "")
                    if base.endswith("_dark"):
                        base_color = base[:-5]
                    candidates.extend([
                        f"{base}.xml",
                        f"{base}_dark.xml",
                        f"{base}_light.xml",
                        f"dark_{base}.xml",
                        f"light_{base}.xml",
                    ])
                    chosen = next((c for c in candidates if c in themes), None)
                if not chosen:
                    chosen = "dark_teal.xml" if "dark_teal.xml" in themes else (themes[0] if themes else None)
                if chosen:
                    apply_stylesheet(app, theme=chosen)
        except Exception:
            # fallback to our dark theme
            self._apply_theme("Material Dark")
        else:
            self._current_theme = chosen or theme
        finally:
            try:
                self._sync_theme_actions()
            except Exception:
                pass
            # Re-apply rounded corners overlay after theme changes
            try:
                self._apply_rounded_corners(8)
            except Exception:
                pass

    def _sync_theme_actions(self) -> None:
        # Reflect current theme selection in checkable actions
        if not hasattr(self, "_theme_actions"):
            return
        cur = self._current_theme or ""
        for key, act in self._theme_actions.items():
            try:
                act.setChecked(key == cur)
            except Exception:
                pass

    # ----- Notifications & Highlights -----
    def _set_sound_enabled(self, en: bool) -> None:
        self._sound_enabled = en

    def _edit_highlight_words(self) -> None:
        cur = ", ".join(self._highlight_keywords)
        text, ok = QInputDialog.getText(self, "Highlight Words", "Comma-separated keywords:", text=cur)
        if ok:
            self._highlight_keywords = [w.strip() for w in text.split(",") if w.strip()]

    def _choose_font(self) -> None:
        try:
            from PyQt6.QtWidgets import QFontDialog
        except Exception:
            return
        ok = False
        font, ok = QFontDialog.getFont(QFont(), self, "Choose Application Font")
        if ok:
            # Some fonts may report pointSize() == -1 (using pixel size). Force a sane default.
            if font.pointSize() <= 0:
                font.setPointSize(10)
            self.windowHandle()  # ensure created
            self.setFont(font)
            # also set in application for consistency
            from PyQt6.QtWidgets import QApplication
            app = QApplication.instance()
            if app:
                app.setFont(font)

    def _set_corner_radius(self, px: int) -> None:
        if _theme_manager is None:
            return
        tm = _theme_manager()
        tm.set_var("radius", f"{px}px")
        tm.apply()
        
    # ----- Bridge callbacks -----
    def _on_message(self, nick: str, target: str, text: str, ts: float) -> None:
        # Route to chat only if matches current channel
        cur = self.bridge.current_channel()
        if target and target == cur:
            self.chat.append(self._format_message_html(nick, self._strip_irc_codes(text), ts))
        # URL grabber
        try:
            self.url_grabber.add_from_text(self._strip_irc_codes(text))
        except Exception:
            pass
        # Unread/highlight counters
        if target:
            if target != cur:
                self._unread[target] = self._unread.get(target, 0) + 1
            # basic highlight: mention of our nick or keywords
            hl = False
            low = (text or '').lower()
            if self._my_nick and self._my_nick.lower() in low:
                hl = True
            else:
                for w in self._highlight_keywords:
                    if w.lower() in low:
                        hl = True
                        break
            if hl:
                self._highlights[target] = self._highlights.get(target, 0) + 1
                # tray notification
                try:
                    if self.tray is not None:
                        self.tray.showMessage(f"Highlight in {target}", f"{nick}: {text}", QSystemTrayIcon.MessageIcon.Information, 5000)
                except Exception:
                    pass
                # sound
                try:
                    if self._sound_enabled and self._sound is not None:
                        # Use system beep if no source set
                        self._sound.play()
                except Exception:
                    pass
                # update sidebar labels
                try:
                    self.sidebar.set_unread(target, self._unread.get(target, 0), self._highlights.get(target, 0))
                except Exception:
                    pass
        # Logging
        try:
            self.logger.append("irc", target or cur or "status", f"<{nick}> {text}", ts)
        except Exception:
            pass

    def _on_names(self, channel: str, names: list[str]) -> None:
        self.members.set_members(names)
        # Provide names to composer for tab completion
        try:
            self.composer.set_completion_names(names)
        except Exception:
            pass

    def _on_channel_clicked(self, ch: str) -> None:
        if ch:
            self.bridge.set_current_channel(ch)

    def _connect_default(self) -> None:
        # Optionally read defaults from a config later
        try:
            channels = ["#peach", "#python"]
        except Exception:
            channels = ["#peach"]
        # Fire and forget: async slot will run under qasync loop
        try:
            import random
            nick = f"DeadRabbit{random.randint(1000, 9999)}"
            self._schedule_async(self.bridge.connectHost, "irc.libera.chat", 6697, True, nick, "peach", "Peach Client", channels, None, None, False)
        except Exception:
            try:
                import random
                nick = f"DeadRabbit{random.randint(1000, 9999)}"
                self.bridge.connectHost("irc.anonops.com", 6697, True, nick, "peach", "Peach Client", channels, None, None, False)
            except Exception:
                pass

    def _open_connect_dialog(self) -> None:
        dlg = ConnectDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            vals = dlg.values()
            # Unpack new signature with remember/autoconnect
            host, port, tls, nick, user, realname, chans, password, sasl_user, remember, autoconnect = vals
            # Harden: normalize host before resolving policy
            host = self._normalize_host(host)
            host, port, tls = self._resolve_connect_policy(host, port, tls)
            # Persist if requested
            if remember:
                self._save_server_settings(host, port, tls, nick, user, realname, chans, bool(autoconnect), password, sasl_user)
                # Also save into multi-server store with a name
                name, ok = QInputDialog.getText(self, "Save Server", "Enter a name for this server:", text=f"{host}:{port}")
                if ok and name.strip():
                    self._servers_save(name.strip(), host, port, tls, nick, user, realname, chans, bool(autoconnect), password, sasl_user)
            # Fire and forget: async slot
            try:
                self._schedule_async(self.bridge.connectHost, host, port, tls, nick, user, realname, chans, password, sasl_user, False)
                if getattr(self, "_auto_negotiate", True):
                    self._schedule_async(self._negotiate_on_connect, host, nick, user, password, sasl_user)
            except Exception:
                # Fallback: direct call if bridge is sync in this build
                try:
                    self.bridge.connectHost(host, port, tls, nick, user, realname, chans, password, sasl_user, False)
                    if getattr(self, "_auto_negotiate", True):
                        self._schedule_async(self._negotiate_on_connect, host, nick, user, password, sasl_user)
                except Exception:
                    pass
            self.status.showMessage(f"Connecting to {host}:{port}…", 2000)
            self._my_nick = nick

    # ----- Connection policy and negotiation -----
    def _resolve_connect_policy(self, host: str, port: int, tls: bool) -> tuple[str, int, bool]:
        """Apply heuristics and user prefs to decide TLS usage and possibly port.

        - If prefer TLS: ensure tls=True for known secure ports (6697, 443, 1337).
        - If prefer TLS and current tls=False but port looks insecure (e.g., 6667), leave as-is.
        - If prefer TLS and custom port (e.g., 1337), keep user's tls choice unless unset.
        """
        try:
            prefer = bool(getattr(self, "_prefer_tls", True))
            if prefer:
                # Treat 1337 as secure for this app as well
                if int(port) in (6697, 443, 1337):
                    tls = True
            return host, int(port), bool(tls)
        except Exception:
            return host, port, tls

    def _normalize_host(self, host: str | None) -> str:
        """Normalize a hostname from user/settings to avoid common DNS errors.

        - Lowercase and strip whitespace
        - Remove URL schemes (irc://, ircs://, http(s)://)
        - Remove trailing slashes
        - Fix common typos for 'debauchedtea.party'
        """
        try:
            h = (host or "").strip().lower()
            if not h:
                return ""
            # Strip schemes
            for pref in ("irc://", "ircs://", "http://", "https://"):
                if h.startswith(pref):
                    h = h[len(pref):]
                    break
            # Remove path part if present
            if "/" in h:
                h = h.split("/", 1)[0]
            # Known typo fixes
            typo_map = {
                "debachedtea.party": "debauchedtea.party",
                "debauchedtea.pary": "debauchedtea.party",
                "debauchedtea.paty": "debauchedtea.party",
                "debauchedtea.part": "debauchedtea.party",
            }
            if h in typo_map:
                h = typo_map[h]
            return h
        except Exception:
            return host or ""

    def _negotiate_on_connect(self, host: str, nick: str | None, user: str | None,
                               password: str | None, sasl_user: str | None) -> None:
        """Minimal IRCv3 CAP and optional SASL negotiation.

        Best-effort via raw commands; safe to call even if server ignores.
        """
        try:
            # Initialize negotiation state
            self._cap_state = {
                'host': host,
                'ls': set(),
                'ack': set(),
                'nak': set(),
                'pending': set(),
                'sasl_requested': False,
                'sasl_in_progress': False,
                'sasl_done': False,
                'end_sent': False,
                'using_tls': False,
            }
            # Try to infer TLS in use from last connect params if available
            try:
                self._cap_state['using_tls'] = True if getattr(self, '_last_connect_tls', False) else False
            except Exception:
                pass
            # Save last creds for SASL
            self._cap_state['nick'] = nick or ''
            self._cap_state['sasl_user'] = sasl_user or nick or ''
            self._cap_state['password'] = password or ''

            # Desired capabilities (request intersection after LS)
            want = {
                "server-time", "message-tags", "echo-message",
                "chghost", "away-notify", "account-notify", "multi-prefix",
                "userhost-in-names", "labeled-response"
            }
            if (password or sasl_user):
                want.add("sasl")
            # STARTTLS preference: note it, but actual upgrade likely requires bridge support
            if bool(getattr(self, '_try_starttls', False)) and not self._cap_state['using_tls']:
                # Only mark interest; do not request here unless we can upgrade
                want.add("starttls")
            self._cap_state['want'] = set(want)

            # Begin: request LS; other requests will be sent when LS arrives and we can intersect with available
            self._send_raw("CAP LS 302")
        except Exception:
            pass

    def _negotiate_handle_line(self, raw: str) -> None:
        """Parse server lines for CAP/SASL and drive negotiation state.

        We depend on bridge emitting raw-ish lines via statusChanged; safe to ignore if not applicable.
        """
        if not raw:
            return
        line = raw.strip()
        # Quick checks to avoid overhead
        if " CAP " not in line and not any(t in line for t in (" AUTHENTICATE ", " 90", " 00")):
            return
        st = getattr(self, '_cap_state', None)
        if st is None:
            return
        try:
            # CAP LS
            if " CAP " in line and " LS " in line:
                # Parse caps after ':'
                caps_part = line.split(':', 1)[1] if ':' in line else ''
                avail = set([c.split('=')[0] for c in caps_part.strip().split() if c])
                st['ls'] |= avail
                # Compute intersection and send CAP REQ for what's wanted
                req = (st.get('want') or set()) & st['ls']
                if req:
                    st['pending'] |= req
                    self._send_raw("CAP REQ :" + " ".join(sorted(req)))
                else:
                    # No caps to request; we can end if not doing SASL
                    if not st.get('sasl_requested'):
                        self._send_raw("CAP END")
                        st['end_sent'] = True
                return

            # CAP ACK
            if " CAP " in line and " ACK " in line:
                caps_part = line.split(':', 1)[1] if ':' in line else ''
                acks = set([c.split('=')[0] for c in caps_part.strip().split() if c])
                st['ack'] |= acks
                st['pending'] -= acks
                # SASL start once ACK'd
                if 'sasl' in acks and not st['sasl_in_progress'] and (st.get('password') or st.get('sasl_user')):
                    st['sasl_requested'] = True
                    st['sasl_in_progress'] = True
                    self._send_raw("AUTHENTICATE PLAIN")
                # STARTTLS path (note: likely unsupported without bridge socket upgrade)
                if 'starttls' in acks and not st['using_tls'] and bool(getattr(self, '_try_starttls', False)):
                    self.status.showMessage("Server supports STARTTLS; upgrade not attempted (bridge support required)", 4000)
                # If no pending and no SASL to perform, end
                if not st['pending'] and not st['sasl_in_progress'] and not st['end_sent']:
                    self._send_raw("CAP END")
                    st['end_sent'] = True
                    self._persist_caps_ack()
                return

            # CAP NAK
            if " CAP " in line and " NAK " in line:
                caps_part = line.split(':', 1)[1] if ':' in line else ''
                naks = set([c.split('=')[0] for c in caps_part.strip().split() if c])
                st['nak'] |= naks
                st['pending'] -= naks
                # If no more pending and no SASL active, end
                if not st['pending'] and not st['sasl_in_progress'] and not st['end_sent']:
                    self._send_raw("CAP END")
                    st['end_sent'] = True
                return

            # AUTHENTICATE + (server ready for payload)
            if line.endswith(" AUTHENTICATE +") and st.get('sasl_in_progress'):
                import base64
                u = st.get('sasl_user') or st.get('nick') or ''
                p = st.get('password') or ''
                mech = base64.b64encode((u + "\0" + u + "\0" + p).encode("utf-8")).decode("ascii")
                self._send_raw("AUTHENTICATE " + mech)
                return

            # SASL numerics handling
            # Success: 900 (logged in), 903 (SASL success)
            if any(code in line.split()[:2] for code in ("900", "903")) and st.get('sasl_in_progress'):
                st['sasl_in_progress'] = False
                st['sasl_done'] = True
                if not st['end_sent']:
                    self._send_raw("CAP END")
                    st['end_sent'] = True
                    self._persist_caps_ack()
                self.status.showMessage("SASL authentication successful", 3000)
                return

            # Failures: 902 not logged in; 904-908 errors depending on server
            if any(code in line.split()[:2] for code in ("902", "904", "905", "906", "907", "908")) and st.get('sasl_in_progress'):
                st['sasl_in_progress'] = False
                st['sasl_done'] = False
                if not st['end_sent']:
                    self._send_raw("CAP END")
                    st['end_sent'] = True
                    self._persist_caps_ack()
                self.status.showMessage("SASL authentication failed", 4000)
                return
        except Exception:
            pass

    def _persist_caps_ack(self) -> None:
        """Persist only the ACK’d capabilities to settings for the current host.
        Stores both a legacy key and a namespaced key by host for multi-server usage.
        """
        try:
            st = getattr(self, '_cap_state', None)
            if not st:
                return
            ack = sorted(st.get('ack') or [])
            host = st.get('host') or ''
            s = QSettings("Peach", "PeachClient")
            # Legacy
            s.setValue("server/capabilities_enabled", ack)
            # Host-scoped
            s.setValue(f"network/server_caps/{host}", ack)
        except Exception:
            pass

    # ----- Multi-server storage (QSettings: group 'servers') -----
    def _servers_list(self) -> list[str]:
        try:
            s = QSettings("Peach", "PeachClient")
            names = s.value("servers/names", [], type=list) or []
            return list(names)
        except Exception:
            return []

    def _servers_save(self, name: str, host: str, port: int, tls: bool, nick: str, user: str, realname: str,
                      channels: list[str], autoconnect: bool, password: str | None, sasl_user: str | None,
                      ignore_invalid_certs: bool = False) -> None:
        try:
            s = QSettings("Peach", "PeachClient")
            names = set(self._servers_list())
            names.add(name)
            s.setValue("servers/names", list(names))
            base = f"servers/{name}"
            s.setValue(base + "/host", host)
            s.setValue(base + "/port", int(port))
            s.setValue(base + "/tls", bool(tls))
            s.setValue(base + "/nick", nick)
            s.setValue(base + "/user", user)
            s.setValue(base + "/realname", realname)
            s.setValue(base + "/channels", list(channels or []))
            s.setValue(base + "/autoconnect", bool(autoconnect))
            s.setValue(base + "/ignore_invalid_certs", bool(ignore_invalid_certs))
            if password:
                s.setValue(base + "/password", password)
            if sasl_user:
                s.setValue(base + "/sasl_user", sasl_user)
        except Exception:
            pass

    def _servers_load(self, name: str) -> tuple | None:
        try:
            s = QSettings("Peach", "PeachClient")
            base = f"servers/{name}"
            host = s.value(base + "/host", type=str)
            if not host:
                return None
            port = s.value(base + "/port", 6697, type=int)
            tls = s.value(base + "/tls", True, type=bool)
            nick = s.value(base + "/nick", type=str)
            user = s.value(base + "/user", type=str)
            realname = s.value(base + "/realname", type=str)
            channels = s.value(base + "/channels", [], type=list) or []
            password = s.value(base + "/password", None, type=str)
            sasl_user = s.value(base + "/sasl_user", None, type=str)
            autoconnect = s.value(base + "/autoconnect", False, type=bool)
            ignore_invalid_certs = s.value(base + "/ignore_invalid_certs", False, type=bool)
            return host, int(port), bool(tls), nick, user or "peach", realname or "Peach Client", list(channels), password, sasl_user, bool(autoconnect), bool(ignore_invalid_certs)
        except Exception:
            return None

    def _servers_delete_name(self, name: str) -> None:
        try:
            s = QSettings("Peach", "PeachClient")
            names = [n for n in self._servers_list() if n != name]
            s.setValue("servers/names", names)
            base = f"servers/{name}"
            for key in ("host","port","tls","nick","user","realname","channels","password","sasl_user","autoconnect","ignore_invalid_certs"):
                s.remove(base + "/" + key)
        except Exception:
            pass

    def _servers_delete(self, name: str) -> None:
        """Compatibility shim: older code may call _servers_delete(name).

        Forward to _servers_delete_name to remove the saved server entry.
        """
        try:
            self._servers_delete_name(name)
        except Exception:
            pass

    def _servers_get_autoconnect(self) -> tuple | None:
        try:
            for n in self._servers_list():
                data = self._servers_load(n)
                if data and data[-2] is True:
                    host, port, tls, nick, user, realname, channels, password, sasl_user, _auto, ignore = data
                    # Include name so we can update its channels later
                    return n, host, port, tls, nick, user, realname, channels, password, sasl_user, ignore
        except Exception:
            pass
        return None

    def _servers_set_autoconnect_name(self, name: str | None) -> None:
        try:
            s = QSettings("Peach", "PeachClient")
            for n in self._servers_list():
                base = f"servers/{n}"
                s.setValue(base + "/autoconnect", bool(name and n == name))
        except Exception:
            pass

    # ----- Servers menu handlers -----
    def _servers_connect(self) -> None:
        names = self._servers_list()
        if not names:
            self.toast_host.show_toast("No saved servers")
            return
        name, ok = QInputDialog.getItem(self, "Connect to Server", "Choose:", names, 0, False)
        if not ok or not name:
            return
        data = self._servers_load(name)
        if not data:
            self.toast_host.show_toast("Server not found")
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, _auto, ignore = data
        # Record current saved server name for persistence of channels
        self._current_server_name = name
        host = self._normalize_host(host)
        host, port, tls = self._resolve_connect_policy(host, port, tls)
        if tls:
            # Apply per-server TLS ignore-invalid-certs preference if applicable
            try:
                self._apply_tls_ignore_setting(ignore)
            except Exception:
                pass
        try:
            self._schedule_async(self.bridge.connectHost, host, port, tls, nick, user, realname, chans, password, sasl_user)
            if getattr(self, "_auto_negotiate", True):
                self._schedule_async(self._negotiate_on_connect, host, nick, user, password, sasl_user)
            self.status.showMessage(f"Connecting to {host}:{port}…", 2000)
            self._my_nick = nick
        except Exception:
            pass

    def _servers_add(self) -> None:
        dlg = ConnectDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            vals = dlg.values()
            host, port, tls, nick, user, realname, chans, password, sasl_user, remember, autoconnect = vals
            name, ok = QInputDialog.getText(self, "Add Server", "Name:", text=f"{host}:{port}")
            if ok and name.strip():
                self._servers_save(name.strip(), host, port, tls, nick, user, realname, chans, bool(autoconnect), password, sasl_user, False)

    def _servers_edit(self) -> None:
        names = self._servers_list()
        if not names:
            self.toast_host.show_toast("No saved servers")
            return
        name, ok = QInputDialog.getItem(self, "Edit Server", "Choose:", names, 0, False)
        if not ok or not name:
            return
        data = self._servers_load(name)
        if not data:
            self.toast_host.show_toast("Server not found")
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, autoconnect, ignore = data
        dlg = ConnectDialog(self)
        # Pre-fill via dialog setters if available; otherwise rely on internal defaults
        try:
            dlg.set_values(host, port, tls, nick, user, realname, chans, password, sasl_user, True, autoconnect)
        except Exception:
            pass
        if dlg.exec() == dlg.DialogCode.Accepted:
            vals = dlg.values()
            host, port, tls, nick, user, realname, chans, password, sasl_user, remember, autoconnect = vals
            self._servers_save(name, host, port, tls, nick, user, realname, chans, bool(autoconnect), password, sasl_user, bool(ignore))

    def _servers_set_ignore_invalid_certs(self) -> None:
        names = self._servers_list()
        if not names:
            self.toast_host.show_toast("No saved servers")
            return
        name, ok = QInputDialog.getItem(self, "Ignore Invalid Certs", "Choose:", names, 0, False)
        if not ok or not name:
            return
        # Ask desired state
        state, ok2 = QInputDialog.getItem(self, "Ignore Invalid Certs", "Set to:", ["Yes", "No"], 0, False)
        if not ok2:
            return
        val = (state == "Yes")
        data = self._servers_load(name)
        if not data:
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, autoconnect, _ignore = data
        self._servers_save(name, host, port, tls, nick, user, realname, chans, bool(autoconnect), password, sasl_user, val)

    def _apply_tls_ignore_setting(self, ignore: bool) -> None:
        try:
            if ignore is True:
                for meth in ("setTlsVerify", "setVerifySsl", "set_ssl_verify", "set_tls_verify"):
                    fn = getattr(self.bridge, meth, None)
                    if callable(fn):
                        try:
                            fn(False)
                            return
                        except Exception:
                            pass
        except Exception:
            pass

    def _servers_delete_prompt(self) -> None:
        names = self._servers_list()
        if not names:
            self.toast_host.show_toast("No saved servers")
            return
        name, ok = QInputDialog.getItem(self, "Delete Server", "Choose:", names, 0, False)
        if ok and name:
            self._servers_delete_name(name)

    def _servers_set_autoconnect(self) -> None:
        names = self._servers_list()
        if not names:
            self.toast_host.show_toast("No saved servers")
            return
        current = None
        try:
            for n in names:
                d = self._servers_load(n)
                if d and d[-1] is True:
                    current = n
                    break
        except Exception:
            pass
        name, ok = QInputDialog.getItem(self, "Set Auto-connect", "Choose:", names, names.index(current) if current in names else 0, False)
        if ok and name:
            self._servers_set_autoconnect_name(name)

    def _on_channels_updated(self, channels: list[str]) -> None:
        """Populate the sidebar with channels received from the bridge and select the first."""
        try:
            # Preserve existing PM entries, then merge with incoming channels
            preserve = [lbl for lbl in getattr(self, "_channel_labels", []) if str(lbl).startswith("[PM:")]
            new_labels = list(channels or [])
            for lbl in preserve:
                if lbl not in new_labels:
                    new_labels.append(lbl)
            # Update union list and sidebar
            self._channel_labels = new_labels
            self.sidebar.set_channels(self._channel_labels)
            # Reset counters for unknown channels
            for k in list(self._unread.keys()):
                if k not in self._channel_labels:
                    del self._unread[k]
            for k in list(self._highlights.keys()):
                if k not in self._channel_labels:
                    del self._highlights[k]
            # If nothing selected, pick the first available
            if not self.bridge.current_channel() and self._channel_labels:
                self.bridge.set_current_channel(self._channel_labels[0])
            # Persist the channel list for autoconnect on next run
            try:
                s = QSettings("Peach", "PeachClient")
                # Extract plain channel names for the current network only
                # Bridge emits composite labels like "net:#chan". We shouldn't persist those.
                cur = self.bridge.current_channel() or ""
                cur_net = cur.split(":", 1)[0] if (":" in cur and not cur.startswith("[")) else None
                def _to_plain(lst: list[str]) -> list[str]:
                    plain: list[str] = []
                    for lbl in lst or []:
                        # Skip pseudo-labels like [PM:...] or [AI:...]
                        if not lbl or lbl.startswith("["):
                            continue
                        # Keep only channels for the current network if known
                        if ":" in lbl and not lbl.startswith("["):
                            net, ch = lbl.split(":", 1)
                            if cur_net and net != cur_net:
                                continue
                            lbl = ch
                        # At this point lbl should be a raw channel like #chan
                        if lbl and (lbl.startswith('#') or lbl.startswith('&')):
                            if lbl not in plain:
                                plain.append(lbl)
                    return plain
                plain_channels = _to_plain(list(channels or []))
                # Save to legacy single-server store
                s.setValue("server/channels", plain_channels)
                # And to active saved server if known
                if self._current_server_name:
                    base = f"servers/{self._current_server_name}"
                    s.setValue(base + "/channels", plain_channels)
            except Exception:
                pass
        except Exception:
            pass

    def _on_current_channel_changed(self, ch: str) -> None:
        # Reset unread count for the active channel and update sidebar badge
        try:
            if ch:
                self._unread[ch] = 0
                hl = self._highlights.get(ch, 0)
                try:
                    self.sidebar.set_unread(ch, 0, hl)
                except Exception:
                    pass
                # Best-effort: select channel in sidebar if API exists
                try:
                    sel = getattr(self.sidebar, 'select_channel', None)
                    if callable(sel):
                        sel(ch)
                except Exception:
                    pass
                self.status.showMessage(f"Switched to {ch}", 1500)
        except Exception:
            pass

    # ----- AI integration -----
    def _start_ai_chat(self) -> None:
        # Ask for model name (only requirement)
        model, ok = QInputDialog.getText(self, "AI Model", "Enter Ollama model name:", text="llama3")
        if not ok or not model.strip():
            return
        if not is_server_up():
            self.toast_host.show_toast("Ollama server not reachable at localhost:11434")
            return
        label = f"[AI:{model.strip()}]"
        # Register AI pseudo-channel without wiping existing entries
        if label not in self._channel_labels:
            self._channel_labels.append(label)
            try:
                self.sidebar.set_channels(self._channel_labels)
                self.sidebar.set_unread(label, 0, 0)
            except Exception:
                pass
        # Switch to AI channel
        self.bridge.set_current_channel(label)
        self.chat.append(f"<i>AI session started with model: {model.strip()}</i>")
        # Auto greet to verify connectivity
        try:
            self.chat.append("<i>Peach:</i> sending hello…")
            self._run_ai_inference(label, "hello")
        except Exception:
            pass

    def _run_ai_inference(self, ai_channel: str, prompt: str) -> None:
        # Extract model name from channel label [AI:model]
        model = ai_channel[4:-1] if ai_channel.startswith("[AI:") and ai_channel.endswith("]") else ai_channel
        # Stop previous worker if any
        if hasattr(self, "_ai_thread") and self._ai_thread is not None:
            try:
                self._ai_worker.stop()
            except Exception:
                pass
            self._ai_thread.quit()
            self._ai_thread.wait()
        self._ai_thread = QThread(self)
        self._ai_worker = OllamaStreamWorker(model=model, prompt=prompt)
        self._ai_worker.moveToThread(self._ai_thread)
        self._ai_thread.started.connect(self._ai_worker.run)
        self._ai_worker.chunk.connect(self._ai_chunk)
        self._ai_worker.done.connect(self._ai_done)
        self._ai_worker.error.connect(self._ai_error)
        self._ai_worker.done.connect(self._ai_thread.quit)
        self._ai_worker.error.connect(self._ai_thread.quit)
        # Start stream and show AI header line
        self.chat.append("<b>AI:</b> ")
        # reset buffer for routing
        self._ai_accum = ""
        self._ai_stream_open = True
        self._ai_thread.start()

    def _ai_chunk(self, text: str) -> None:
        # Append incremental text to the last line
        cursor = self.chat.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self.chat.setTextCursor(cursor)
        # Accumulate for routing if enabled and stream out on thresholds
        if self._ai_route_target:
            self._ai_accum += text
            # Flush heuristics: newline, sentence end, or buffer too large
            if ("\n" in text) or text.endswith(('. ', '! ', '? ')) or len(self._ai_accum) >= 320:
                self._flush_ai_route_buffer()

    def _ai_done(self) -> None:
        self._ai_stream_open = False
        self.status.showMessage("AI response complete", 1500)
        # Final flush of any remaining routed text
        if self._ai_route_target:
            self._flush_ai_route_buffer(final_flush=True)

    def _ai_error(self, msg: str) -> None:
        self._ai_stream_open = False
        self.toast_host.show_toast(f"AI error: {msg}")

    # ----- AI routing -----
    def _choose_ai_route_target(self) -> None:
        # Build list of IRC composite channels (exclude AI entries)
        options = [c for c in self._channel_labels if not c.startswith("[AI:") and ":" in c]
        if not options:
            self.toast_host.show_toast("No IRC channels available to route to")
            return
        current = self.bridge.current_channel() or ""
        if current not in options:
            current = options[0]
        item, ok = QInputDialog.getItem(self, "Route AI Output", "Choose target channel:", options, options.index(current) if current in options else 0, False)
        if ok and item:
            self._ai_route_target = item
            try:
                self.act_ai_route_stop.setEnabled(True)
            except Exception:
                pass
            self.status.showMessage(f"AI output will be routed to {item}", 2500)

    def _stop_ai_route(self) -> None:
        self._ai_route_target = None
        try:
            self.act_ai_route_stop.setEnabled(False)
        except Exception:
            pass
        self.status.showMessage("AI output routing stopped", 2000)

    def _flush_ai_route_buffer(self, final_flush: bool = False) -> None:
        """Send buffered AI output to the selected IRC channel in safe chunks.

        Splits on whitespace up to ~400 chars per message. Prefix the first part with 'AI: '.
        Clears the buffer if send succeeds.
        """
        tgt = self._ai_route_target
        buf = (self._ai_accum or "").strip()
        if not tgt or not buf:
            return
        # Split into <= 400 char parts, prefer word boundaries
        parts: list[str] = []
        s = buf
        limit = 400
        while s:
            if len(s) <= limit:
                parts.append(s)
                break
            cut = s.rfind(' ', 0, limit)
            if cut == -1:
                cut = limit
            parts.append(s[:cut])
            s = s[cut:].lstrip()
        # Prefix first part
        if parts:
            parts[0] = f"AI: {parts[0]}"
        try:
            for p in parts:
                # fire-and-forget; Bridge slot is async
                self.bridge.sendMessageTo(tgt, p)
            self.status.showMessage(f"Routed AI output to {tgt}", 1500)
            # Clear buffer after successful send, unless we want to keep trailing text mid-stream
            self._ai_accum = "" if final_flush or len(self._ai_accum) >= 320 else ""
        except Exception:
            self.toast_host.show_toast("Failed to route AI output")
