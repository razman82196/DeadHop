from __future__ import annotations

import asyncio
import json
import re
import shutil
import time

from PyQt6.QtCore import QByteArray, QSettings, QSize, Qt, QThread, QUrl
from PyQt6.QtGui import (
    QAction,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
    QPalette,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDockWidget,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStatusBar,
    QSystemTrayIcon,
    QTextEdit,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..ai.ollama import is_server_up
from .ai_worker import OllamaStreamWorker
from .bridge import BridgeQt
from .dialogs.connect_dialog import ConnectDialog
from .dialogs.emoji_picker import pick_emoji
from .dialogs.giphy_dialog import pick_gif
from .dialogs.modes_dialog import ModesDialog
from .dialogs.topic_dialog import TopicDialog
from .widgets.composer import Composer
from .widgets.find_bar import FindBar
from .widgets.friends_dock import FriendsDock
from .widgets.members_view import MembersView
from .widgets.sidebar_tree import SidebarTree
from .widgets.toast import ToastHost
from .widgets.url_grabber import URLGrabber
from .widgets.video_panel import VideoPanel

try:
    from .theme import theme_manager as _theme_manager
except Exception:
    _theme_manager = None
from pathlib import Path

from ..logging.log_writer import LogWriter

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

    def _on_friends_changed(self, friends: list[str]) -> None:
        """Persist friends, push to bridge MONITOR, and resync presence maps."""
        try:
            s = QSettings("DeadHop", "DeadHopClient")
            s.setValue("friends", list(friends or []))
        except Exception:
            pass

        # Settings dialog launcher removed (was incorrectly added here)
        # Update MONITOR list (async)
        try:
            self._schedule_async(self.bridge.setMonitorList, list(friends or []))
        except Exception:
            pass
        # Trim avatar entries for removed friends (optional; keep non-friends avatars for members)
        try:
            # Keep as-is to allow member avatars even if not in friends
            self.friends.set_avatars(self._avatar_map)
        except Exception:
            pass

    def _on_avatars_changed(self, avatars: dict) -> None:
        """Receive avatar map from FriendsDock and propagate to views + persist."""
        try:
            self._avatar_map = dict(avatars or {})
            # Push to widgets
            try:
                self.friends.set_avatars(self._avatar_map)
            except Exception:
                pass
            # No settings dialog handling here; only update avatars in views and persist
            try:
                self.members.set_avatars(self._avatar_map)
            except Exception:
                pass
            # Persist
            try:
                s = QSettings("DeadHop", "DeadHopClient")
                s.setValue("avatars", dict(self._avatar_map))
            except Exception:
                pass
        except Exception:
            pass

    def _on_monitor_online(self, nicks: list[str]) -> None:
        if not nicks:
            return
        try:
            self._online_set.update(n.strip() for n in nicks if n)
            # Update views
            try:
                self.friends.set_presence(self._online_set)
            except Exception:
                pass
            try:
                self.members.set_presence(self._online_set)
            except Exception:
                pass
            # Notifications
            if getattr(self, "_notify_presence_online", True):
                for n in nicks:
                    msg = f"{n} is online"
                    try:
                        self.toast_host.show_toast(msg)
                    except Exception:
                        pass
                    if getattr(self, "_notify_presence_system", True) and getattr(
                        self, "tray", None
                    ):
                        try:
                            self.tray.showMessage(
                                "Friend online", msg, QSystemTrayIcon.MessageIcon.Information, 2500
                            )
                        except Exception:
                            pass
                    if getattr(self, "_notify_presence_sound", False):
                        try:
                            if self._sound_enabled:
                                se = getattr(self, "_se_presence", None)
                                if se:
                                    se.play()
                                else:
                                    from PyQt6.QtWidgets import QApplication

                                    QApplication.beep()
                        except Exception:
                            pass
        except Exception:
            pass

    def _on_monitor_offline(self, nicks: list[str]) -> None:
        if not nicks:
            return
        try:
            self._online_set.difference_update(n.strip() for n in nicks if n)
            # Update views
            try:
                self.friends.set_presence(self._online_set)
            except Exception:
                pass
            try:
                self.members.set_presence(self._online_set)
            except Exception:
                pass
            # Notifications
            if getattr(self, "_notify_presence_offline", False):
                for n in nicks:
                    msg = f"{n} went offline"
                    try:
                        self.toast_host.show_toast(msg)
                    except Exception:
                        pass
                    if getattr(self, "_notify_presence_system", True) and getattr(
                        self, "tray", None
                    ):
                        try:
                            self.tray.showMessage(
                                "Friend offline", msg, QSystemTrayIcon.MessageIcon.Warning, 2500
                            )
                        except Exception:
                            pass
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
        self.setWindowTitle("DeadHop")
        self.resize(1200, 800)
        self.bridge = BridgeQt()
        # In-memory scrollback per channel/label -> list[HTML]
        self._scrollback: dict[str, list[str]] = {}
        self._scrollback_limit: int = 1000
        # Filesystem location for persisted scrollback
        try:
            from PyQt6.QtCore import QStandardPaths

            base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        except Exception:
            base = None
        self._scrollback_dir = base
        # Notification preferences (defaults)
        self._notify_on_pm = True
        self._notify_on_mention = True
        self._notify_on_highlight = True
        self._notify_on_join_part = True
        # Settings defaults (defensive init so closeEvent/_save_settings never crash)
        self._current_theme: str | None = None
        self._word_wrap: bool = True
        self._show_timestamps: bool = False
        self._chat_font_family: str | None = None
        self._chat_font_size: int | None = None
        self._highlight_keywords: list[str] = []
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
        # Our current nick (used for highlight detection); set on connect/nick events
        self._my_nick: str = ""
        self._sound_enabled: bool = True
        try:
            from PyQt6.QtMultimedia import QSoundEffect

            self._sound = QSoundEffect(self)
            self._sound.setSource(QUrl.fromLocalFile(""))  # legacy presence beep
            # Message and highlight sounds
            self._se_msg = QSoundEffect(self)
            self._se_hl = QSoundEffect(self)
            self._se_presence = QSoundEffect(self)
            try:
                s = QSettings("DeadHop", "DeadHopClient")
                msg_path = s.value("notify/sound_msg", "", str)
                hl_path = s.value("notify/sound_hl", "", str)
                pr_path = s.value("notify/sound_presence", "", str)
                vol = float(s.value("notify/sound_volume", 0.7))
                # Sanitize unsupported formats (QSoundEffect typically supports WAV/OGG). Skip MP3.
                try:

                    def _ok(p: str) -> bool:
                        if not p:
                            return False
                        ext = Path(p).suffix.lower()
                        return ext in {".wav", ".ogg"}

                    if msg_path and not _ok(msg_path):
                        msg_path = ""
                    if hl_path and not _ok(hl_path):
                        hl_path = ""
                    if pr_path and not _ok(pr_path):
                        pr_path = ""
                except Exception:
                    pass
                # If any are unset, pick sensible defaults from resources/sounds
                try:
                    snd_dir = Path(__file__).resolve().parents[1] / "resources" / "sounds"
                    files: list[str] = []
                    if snd_dir.exists():
                        wavs = [str(p) for p in snd_dir.glob("*.wav")]
                        oggs = [str(p) for p in snd_dir.glob("*.ogg")]
                        files = wavs + oggs

                    def choose(name_part: str) -> str:
                        for f in files:
                            if name_part.lower() in Path(f).name.lower():
                                return f
                        return files[0] if files else ""

                    if not msg_path:
                        cand = choose("message") or choose("sms")
                        if cand:
                            msg_path = cand
                            s.setValue("notify/sound_msg", msg_path)
                    if not hl_path:
                        cand = choose("highlight") or choose("whistle") or choose("sms")
                        if cand:
                            hl_path = cand
                            s.setValue("notify/sound_hl", hl_path)
                    if not pr_path:
                        cand = choose("presence") or choose("icq") or choose("online")
                        if cand:
                            pr_path = cand
                            s.setValue("notify/sound_presence", pr_path)
                except Exception:
                    pass
                if msg_path:
                    self._se_msg.setSource(QUrl.fromLocalFile(msg_path))
                if hl_path:
                    self._se_hl.setSource(QUrl.fromLocalFile(hl_path))
                if pr_path:
                    self._se_presence.setSource(QUrl.fromLocalFile(pr_path))
                try:
                    self._se_msg.setVolume(vol)
                    self._se_hl.setVolume(vol)
                    self._se_presence.setVolume(vol)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            self._sound = None
            self._se_msg = None
            self._se_hl = None
            self._se_presence = None

        # Central area: sidebar | chat | members using splitters
        central = QWidget(self)
        self.setCentralWidget(central)
        root_v = QVBoxLayout(central)
        root_v.setContentsMargins(0, 0, 0, 0)
        root_v.setSpacing(0)

        # Set window/app icon from resources/icons if available
        try:
            icons_dir = Path(__file__).resolve().parents[1] / "resources" / "icons"
            cand = None
            for ext in (".ico", ".png", ".svg"):  # prefer .ico
                found = list(icons_dir.glob(f"*{ext}"))
                if found:
                    cand = found[0]
                    break
            if cand is not None:
                self.setWindowIcon(QIcon(str(cand)))
        except Exception:
            pass

        # Top toolbar removed per UI simplification

        # Sidebar tree (Network > Channels)
        self.sidebar = SidebarTree()
        self.sidebar.channelSelected.connect(self._on_channel_clicked)
        try:
            # Optional: server node selection to show MOTD/status
            self.sidebar.networkSelected.connect(self._on_network_selected)
        except Exception:
            pass
        self.sidebar.channelAction.connect(self._on_channel_action)
        try:
            self.sidebar.networkAction.connect(self._on_network_action)
        except Exception:
            pass

        # Chat view switched to QWebEngineView for rich HTML and inline media
        from PyQt6.QtWebEngineWidgets import QWebEngineView  # type: ignore

        self.chat = QWebEngineView(self)
        # Chat webview readiness and buffer for early messages
        self._chat_ready: bool = False
        self._chat_buf: list[str] = []
        try:
            self._init_chat_webview()
        except Exception:
            pass
        # Inline video panel (YouTube)
        self.video_panel = VideoPanel(self)
        try:
            self.video_panel.set_pop_handler(self._open_internal_browser)
        except Exception:
            pass
        # Vertical splitter to host chat and video
        self.split_chat = QSplitter(Qt.Orientation.Vertical)
        self.split_chat.addWidget(self.chat)
        self.split_chat.addWidget(self.video_panel)
        self.split_chat.setStretchFactor(0, 1)
        self.split_chat.setStretchFactor(1, 0)
        # Start with video hidden; splitter will allocate most to chat
        try:
            self.video_panel.hide()
            self.split_chat.setSizes([800, 0])
        except Exception:
            pass

        # Composer
        self.composer = Composer()
        self.composer.messageSubmitted.connect(self._on_submit)
        # Emoji/GIF selectors
        try:
            self.composer.emojiRequested.connect(self._on_emoji_request)
            self.composer.gifRequested.connect(self._on_gif_request)
        except Exception:
            pass

        # Members
        self.members = MembersView()
        self.members.memberAction.connect(self._on_member_action)

        # Splitter layout
        self.split_lr = QSplitter(Qt.Orientation.Horizontal)
        self.split_lr.addWidget(self.sidebar)
        self.split_lr.addWidget(self.split_chat)
        self.split_lr.addWidget(self.members)
        self.split_lr.setStretchFactor(0, 0)
        self.split_lr.setStretchFactor(1, 1)
        self.split_lr.setStretchFactor(2, 0)
        self.split_lr.setSizes([240, 800, 240])
        # Ensure member context menu actions are handled
        try:
            self.members.memberAction.connect(self._on_member_action)
        except Exception:
            pass

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
        # Notification preferences (default ON); load from QSettings
        try:
            s = QSettings("DeadHop", "DeadHopClient")
            self._notify_toast: bool = bool(s.value("notify/toast", True, bool))
            self._notify_tray: bool = bool(s.value("notify/tray", True, bool))
            self._notify_sound: bool = bool(s.value("notify/sound", True, bool))
        except Exception:
            self._notify_toast = True
            self._notify_tray = True
            self._notify_sound = True
        self._init_notifications()

        # Reflect channel list updates from bridge into the sidebar
        try:
            self.bridge.channelsUpdated.connect(self._on_channels_updated)
        except Exception:
            pass

        # IRC Log dock
        self.log_view = QTextEdit(self)
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        self.log_dock = QDockWidget("IRC Log", self)
        self.log_dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_dock.hide()

        # Ensure tray icon has a visible icon to avoid warnings
        try:
            if getattr(self, "tray", None) is not None:
                ic = self.windowIcon()
                if ic.isNull():
                    try:
                        from PyQt6.QtWidgets import QStyle

                        ic = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                    except Exception:
                        pass
                if ic and not ic.isNull():
                    self.tray.setIcon(ic)
                    self.tray.setVisible(True)
        except Exception:
            pass

        # URL Grabber dock
        self.url_grabber = URLGrabber(self)
        self.url_dock = QDockWidget("URLs", self)
        self.url_dock.setWidget(self.url_grabber)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.url_dock)

        # Quick toolbar (top-left): font slider + quick settings
        try:
            self._init_quick_toolbar()
        except Exception:
            pass
        self.url_dock.hide()

        # Standalone in-app browser window (created lazily)
        self.browser_window = None

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
        # Avatars and presence caches
        self._avatar_map: dict[str, str | None] = {}
        self._online_set: set[str] = set()
        # React to friends/avatars edits
        try:
            self.friends.friendsChanged.connect(self._on_friends_changed)
            # Persist avatars and reflect to members view
            if hasattr(self.friends, "avatarsChanged"):
                self.friends.avatarsChanged.connect(self._on_avatars_changed)
        except Exception:
            pass
        # System tray for presence notifications
        try:
            available = False
            try:
                available = QSystemTrayIcon.isSystemTrayAvailable()
            except Exception:
                # If the check fails, assume available and attempt best effort
                available = True
            if available:
                self.tray = QSystemTrayIcon(self)
                app_icon = (
                    get_icon(["app", "logo", "deadhop"]) if "get_icon" in globals() else QIcon()
                )
                if not app_icon.isNull():
                    self.tray.setIcon(app_icon)
                # Basic tray setup: tooltip and visibility
                try:
                    self.tray.setToolTip("DeadHop")
                except Exception:
                    pass
                # Context menu (Show / Hide / Quit)
                try:
                    menu = QMenu(self)
                    act_show = QAction("Show", self)
                    act_show.triggered.connect(self._show_from_tray)
                    menu.addAction(act_show)
                    act_hide = QAction("Hide", self)
                    act_hide.triggered.connect(self._hide_from_tray)
                    menu.addAction(act_hide)
                    menu.addSeparator()
                    act_quit = QAction("Quit", self)
                    act_quit.triggered.connect(self._quit_from_tray)
                    menu.addAction(act_quit)
                    self.tray.setContextMenu(menu)
                except Exception:
                    pass
                self.tray.setVisible(True)
                # Click on tray icon focuses the window
                try:
                    self.tray.activated.connect(self._on_tray_activated)
                except Exception:
                    pass
            else:
                self.tray = None
        except Exception:
            self.tray = None

        # Servers dock (initialized on demand)
        self.servers_dock = None
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
        # Per-network status/MOTD cache (list of recent lines)
        self._status_by_net: dict[str, list[str]] = {}
        # Per-network ISUPPORT (005) map
        self._isupport_by_net: dict[str, dict[str, str]] = {}
        # Prefer typed JOIN/PART/etc. events over raw parsing when available
        self._typed_events: bool = True

        # Menus
        self._build_menus()
        # Toolbar removed

        # Bridge signal wiring
        self.bridge.statusChanged.connect(self._on_status)
        self.bridge.messageReceived.connect(self._on_message)
        self.bridge.namesUpdated.connect(self._on_names)
        self.bridge.currentChannelChanged.connect(self._on_current_channel_changed)
        self.bridge.channelsUpdated.connect(self._on_channels_updated)
        # Typed event wiring (JOIN/PART/QUIT/NICK/TOPIC/MODE)
        try:
            if hasattr(self.bridge, "userJoined"):
                self.bridge.userJoined.connect(self._on_user_joined)
            if hasattr(self.bridge, "userParted"):
                self.bridge.userParted.connect(self._on_user_parted)
            if hasattr(self.bridge, "userQuit"):
                self.bridge.userQuit.connect(self._on_user_quit)
            if hasattr(self.bridge, "userNickChanged"):
                self.bridge.userNickChanged.connect(self._on_user_nick_changed)
            if hasattr(self.bridge, "channelTopic"):
                self.bridge.channelTopic.connect(self._on_channel_topic)
            if hasattr(self.bridge, "channelMode"):
                self.bridge.channelMode.connect(self._on_channel_mode)
            if hasattr(self.bridge, "channelModeUsers"):
                self.bridge.channelModeUsers.connect(self._on_channel_mode_users)
        except Exception:
            pass
        # Presence via MONITOR
        try:
            if hasattr(self.bridge, "monitorOnline"):
                self.bridge.monitorOnline.connect(self._on_monitor_online)
            if hasattr(self.bridge, "monitorOffline"):
                self.bridge.monitorOffline.connect(self._on_monitor_offline)
        except Exception:
            pass

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
        # Cache of NAMES per composite channel label (e.g. "net:#chan")
        self._names_by_channel: dict[str, list[str]] = {}
        # Apply global rounded corners styling overlay
        try:
            self._apply_rounded_corners(8)
        except Exception:
            pass
        #

    def _maybe_migrate_qsettings(self) -> None:
        """Copy settings from legacy Peach/PeachClient to DeadHop/DeadHopClient once.
        Safe and idempotent: uses a marker key to avoid repeated work.
        """
        new = QSettings("DeadHop", "DeadHopClient")
        try:
            if new.value("migrated_from_peach", False, type=bool):
                return
        except Exception:
            # If marker cannot be read, proceed best effort
            pass
        old = QSettings("Peach", "PeachClient")
        try:
            keys = list(old.allKeys() or [])
        except Exception:
            keys = []
        if not keys:
            # Nothing to migrate
            try:
                new.setValue("migrated_from_peach", True)
            except Exception:
                pass
            return
        # Copy keys that don't already exist in new namespace
        for k in keys:
            try:
                if hasattr(new, "contains") and new.contains(k):
                    continue
            except Exception:
                # If contains() unavailable/raises, still attempt a best-effort write
                pass
            try:
                new.setValue(k, old.value(k))
            except Exception:
                pass
        try:
            new.setValue("migrated_from_peach", True)
        except Exception:
            pass

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
        # Sanitize nick from list labels that may include status prefix
        try:
            nick = str(nick or "").lstrip("~&@%+ ").strip()
        except Exception:
            pass
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
                try:
                    self._chat_append(f"<i>WHOIS {nick} (not sent: no raw command API)</i>")
                except Exception:
                    pass
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
            reason, ok = QInputDialog.getText(
                self, "Kick", f"Reason for kicking {nick} from {ch}:", text=""
            )
            if ok:
                sent = False
                for meth, cmd in (
                    ("kickUser", None),
                    ("sendRaw", f"KICK {ch} {nick} :{reason}"),
                    ("sendCommand", f"KICK {ch} {nick} :{reason}"),
                ):
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
            mask, ok = QInputDialog.getText(
                self, "Ban", f"Ban mask or nick for {ch} (e.g. {nick} or *!*@host):", text=nick
            )
            if ok and mask.strip():
                sent = False
                for meth, cmd in (
                    ("setModes", None),
                    ("sendRaw", f"MODE {ch} +b {mask}"),
                    ("sendCommand", f"MODE {ch} +b {mask}"),
                ):
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
            try:
                self._schedule_async(self.bridge.setModes, ch, "+o " + nick)
            except Exception:
                self._send_raw(f"MODE {ch} +o {nick}")
        elif action == "deop":
            ch = self.bridge.current_channel() or ""
            try:
                self._schedule_async(self.bridge.setModes, ch, "-o " + nick)
            except Exception:
                self._send_raw(f"MODE {ch} -o {nick}")
        elif action == "add friend":
            try:
                current = [
                    self.friends.list.item(i).data(Qt.ItemDataRole.UserRole)
                    for i in range(self.friends.list.count())
                ]
                if nick not in current:
                    current.append(nick)
                    self.friends.set_friends(current)
                    try:
                        self._schedule_async(self.bridge.setMonitorList, current)
                    except Exception:
                        pass
                    try:
                        s = QSettings("DeadHop", "DeadHopClient")
                        s.setValue("friends", current)
                    except Exception:
                        pass
                self.toast_host.show_toast(f"Added {nick} to friends")
            except Exception:
                pass
        else:
            self.toast_host.show_toast(f"Action '{action}' for {nick} not yet implemented")

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
            self._schedule_async(
                self.bridge.connectHost,
                host,
                port,
                tls,
                nick or self._default_nick(),
                user,
                realname,
                chans,
                password,
                sasl_user,
                bool(ignore),
            )
            if getattr(self, "_auto_negotiate", True):
                self._schedule_async(
                    self._negotiate_on_connect,
                    host,
                    nick or self._default_nick(),
                    user,
                    password,
                    sasl_user,
                )
            self.status.showMessage(f"Connecting to {host}:{port}…", 2000)
            self._my_nick = nick or self._default_nick()
        except Exception:
            try:
                self.bridge.connectHost(
                    host,
                    port,
                    tls,
                    nick or self._default_nick(),
                    user,
                    realname,
                    chans,
                    password,
                    sasl_user,
                    bool(ignore),
                )
                if getattr(self, "_auto_negotiate", True):
                    self._schedule_async(
                        self._negotiate_on_connect,
                        host,
                        nick or self._default_nick(),
                        user,
                        password,
                        sasl_user,
                    )
            except Exception:
                pass

    def _servers_edit_name(self, name: str) -> None:
        data = self._servers_load(name)
        if not data:
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, autoconnect, ignore = (
            data
        )
        dlg = ConnectDialog(self)
        try:
            dlg.set_values(
                host, port, tls, nick, user, realname, chans, password, sasl_user, True, autoconnect
            )
        except Exception:
            pass
        if dlg.exec() == dlg.DialogCode.Accepted:
            vals = dlg.values()
            (
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
            ) = vals
            self._servers_save(
                name,
                host,
                port,
                tls,
                nick,
                user,
                realname,
                chans,
                bool(autoconnect),
                password,
                sasl_user,
                ignore,
            )

    def _servers_toggle_ignore_name(self, name: str) -> None:
        data = self._servers_load(name)
        if not data:
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, autoconnect, ignore = (
            data
        )
        self._servers_save(
            name,
            host,
            port,
            tls,
            nick,
            user,
            realname,
            chans,
            bool(autoconnect),
            password,
            sasl_user,
            not ignore,
        )
        self.status.showMessage(
            f"Ignore invalid certs: {'Yes' if not ignore else 'No'} for {name}", 1500
        )

    def _show_browser_panel(self) -> None:
        self._ensure_browser_window()
        if not self.browser_window:
            return
        try:
            self.browser_window.show()
            self.browser_window.raise_()
            self.browser_window.activateWindow()
        except Exception:
            pass

    def _import_system_cookies_for_current_site(self) -> None:
        try:
            self._ensure_browser_window()
            if not self.browser_window:
                self.toast_host.show_toast("Browser panel unavailable")
                return
            url = self.browser_window.view.url()
            host = url.host()
            if not host:
                self.toast_host.show_toast("Open a site in the Browser first")
                return
            # Import cookies for this domain
            n = self.browser_window.import_cookies_from_system(domain=host)
            if n > 0:
                self.status.showMessage(f"Imported {n} cookies for {host}", 2500)
                # Reload to apply
                self.browser_window.view.reload()
            else:
                self.toast_host.show_toast("No cookies imported (install browser-cookie3?)")
        except Exception:
            self.toast_host.show_toast("Cookie import failed")

    def _ensure_browser_window(self) -> None:
        if self.browser_window is None:
            try:
                from .widgets.browser_window import BrowserWindow

                self.browser_window = BrowserWindow(self)
            except Exception:
                self.browser_window = None

    def _reset_browser_profile(self) -> None:
        """Delete the persistent internal browser profile and reset the browser.

        Closes and destroys the current browser dock (if any), removes the
        profile directory at app/resources/qtweb/browser, and defers
        re-creation until the browser panel is next requested.
        """
        # 1) Close/hide the window safely
        try:
            if self.browser_window is not None:
                try:
                    self.browser_window.hide()
                except Exception:
                    pass
                try:
                    self.browser_window.deleteLater()
                except Exception:
                    pass
                self.browser_window = None
        except Exception:
            pass
        # 2) Remove the persistent profile dir used by the in-app browser
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
                self.toast_host.show_toast(
                    "Browser profile reset. Open Browser panel to reinitialize."
                )
            except Exception:
                pass
        except Exception:
            try:
                self.toast_host.show_toast("Failed to reset browser profile")
            except Exception:
                pass

    def _toggle_browser_panel(self) -> None:
        self._ensure_browser_window()
        if not self.browser_window:
            return
        if self.browser_window.isVisible():
            self.browser_window.hide()
        else:
            self.browser_window.show()

    def _open_internal_browser(self, url: str | QUrl) -> None:
        """Open a URL in the in-app browser window."""
        try:
            self._ensure_browser_window()
            if self.browser_window:
                self.browser_window.open_url(url)
        except Exception:
            pass

    def _build_menus(self) -> None:
        """Build full menu bar: File, Servers, View, Tools, Help."""
        try:
            mb = self.menuBar()
            mb.clear()

            # File
            m_file = mb.addMenu("&File")
            a_connect = m_file.addAction("&Connect…")
            a_connect.setShortcut(QKeySequence.StandardKey.AddTab)
            a_connect.triggered.connect(self._open_connect_dialog)
            m_file.addSeparator()
            a_quit = m_file.addAction("E&xit")
            a_quit.setShortcut(QKeySequence.StandardKey.Quit)
            try:
                a_quit.triggered.connect(self.close)
            except Exception:
                pass

            # Servers
            m_srv = mb.addMenu("&Servers")
            a_srv_add = m_srv.addAction("&Add…")
            a_srv_add.triggered.connect(self._servers_add)
            a_srv_edit = m_srv.addAction("&Edit…")
            a_srv_edit.triggered.connect(self._servers_edit)
            a_srv_delete = m_srv.addAction("&Delete…")
            a_srv_delete.triggered.connect(self._servers_delete_prompt)
            m_srv.addSeparator()
            a_srv_connect = m_srv.addAction("&Connect to Saved…")
            a_srv_connect.setShortcut(QKeySequence("Ctrl+Shift+C"))
            a_srv_connect.triggered.connect(self._servers_connect)
            a_srv_autoc = m_srv.addAction("Set &Auto-connect…")
            a_srv_autoc.triggered.connect(self._servers_set_autoconnect)
            a_srv_ignore = m_srv.addAction("Ignore Invalid &Certs…")
            a_srv_ignore.triggered.connect(self._servers_set_ignore_invalid_certs)

            # View
            m_view = mb.addMenu("&View")
            a_view_browser = m_view.addAction("Open &Browser Panel")
            a_view_browser.triggered.connect(self._show_browser_panel)
            a_view_toggle = m_view.addAction("&Toggle Browser Panel")
            a_view_toggle.triggered.connect(self._toggle_browser_panel)
            a_view_reset = m_view.addAction("&Reset Browser Profile")
            a_view_reset.triggered.connect(self._reset_browser_profile)
            a_view_cookies = m_view.addAction("&Import Cookies for Current Site")
            a_view_cookies.triggered.connect(self._import_system_cookies_for_current_site)
            m_view.addSeparator()
            a_view_urls = m_view.addAction("Show &URL Grabber")
            a_view_urls.triggered.connect(lambda: self.url_dock.show())
            a_view_friends = m_view.addAction("Show &Friends")
            a_view_friends.triggered.connect(lambda: self.friends_dock.show())
            a_view_log = m_view.addAction("Show &IRC Log")
            a_view_log.triggered.connect(lambda: self.log_dock.show())
            a_view_find = m_view.addAction("&Find…")
            a_view_find.setShortcut(QKeySequence.StandardKey.Find)
            a_view_find.triggered.connect(lambda: self.find_dock.show())

            # Tools
            m_tools = mb.addMenu("&Tools")
            a_ai = m_tools.addAction("Start &AI Chat…")
            a_ai.triggered.connect(self._start_ai_chat)
            a_ai_route = m_tools.addAction("&Route AI Output…")
            a_ai_route.triggered.connect(self._choose_ai_route_target)
            self.act_ai_route_stop = m_tools.addAction("Stop AI &Route")
            self.act_ai_route_stop.setEnabled(False)
            self.act_ai_route_stop.triggered.connect(self._stop_ai_route)
            m_tools.addSeparator()
            a_settings = m_tools.addAction("&Settings…")
            a_settings.setShortcut(QKeySequence.StandardKey.Preferences)
            a_settings.triggered.connect(self._open_settings_dialog)

            # Help
            m_help = mb.addMenu("&Help")
            a_about = m_help.addAction("&About")

            def _about():
                try:
                    QMessageBox.information(self, "About", "DeadHop\nPyQt6 with Qt WebEngine")
                except Exception:
                    pass

            a_about.triggered.connect(_about)
        except Exception:
            pass

    def _on_anchor_clicked(self, url: QUrl) -> None:
        # With QWebEngineView the chat renders inline; keep this as fallback handler
        try:
            s = url.toString()
        except Exception:
            s = ""
        vid = self._youtube_id(s) if s else None
        if vid and hasattr(self, "video_panel") and self.video_panel:
            try:
                self.video_panel.play_youtube_id(vid)
                return
            except Exception:
                pass
        # Fallback to browser window
        try:
            self._ensure_browser_window()
            if self.browser_window:
                self.browser_window.open_url(url)
        except Exception:
            pass

    # ----- Formatting helpers -----
    _URL_RE = re.compile(r"(https?://\S+)")
    _IMG_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
    _VID_EXTS = (".mp4", ".webm", ".mov")

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
        # Build embeds for all URLs and strip URLs from visible text
        embeds: list[str] = []
        embedded_urls: list[str] = []
        for m in self._URL_RE.finditer(safe_text):
            url = m.group(1)
            low = url.lower()
            if any(low.endswith(ext) for ext in self._IMG_EXTS):
                embeds.append(
                    f"<br><img src='{url}' style='border-radius: 8px;' data-msize='small'>"
                )
                embedded_urls.append(url)
                continue
            if any(low.endswith(ext) for ext in self._VID_EXTS):
                embeds.append(
                    "<br>"
                    f"<video data-msize='small' controls src='{url}' preload='metadata'></video>"
                )
                embedded_urls.append(url)
                continue
            yid = self._youtube_id(url)
            if yid:
                embeds.append(
                    "<br>"
                    f"<iframe data-msize='small' width='560' height='315' src='https://www.youtube.com/embed/{yid}'"
                    " title='YouTube video player' frameborder='0'"
                    " allow='accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture'"
                    " allowfullscreen></iframe>"
                )
                embedded_urls.append(url)
        # Strip URLs from displayed text
        display_text = safe_text
        for u in embedded_urls:
            display_text = display_text.replace(u, "")
        display_text = re.sub(r"\s+", " ", display_text).strip()
        embed_html = "".join(embeds)
        prefix = ""
        if getattr(self, "_show_timestamps", False):
            if ts is None:
                ts = time.time()
            t = time.localtime(ts)
            prefix = f"<span class='ts'>[{t.tm_hour:02d}:{t.tm_min:02d}]</span> "
        color = self._nick_color(nick)
        nick_html = f"<span class='nick' style='--nick:{color}'>{nick}</span>"
        return f"{prefix}{nick_html} <span class='msg-text'>{display_text}</span>{embed_html}"

    def _on_emoji_request(self) -> None:
        try:
            em = pick_emoji(self)
            if em:
                cur = self.composer.input.textCursor()
                cur.insertText(em)
                self.composer.input.setTextCursor(cur)
                self.composer.input.setFocus()
        except Exception:
            pass

    def _on_gif_request(self) -> None:
        try:
            try:
                self.status.showMessage("Opening GIPHY…", 2000)
            except Exception:
                pass
            url = pick_gif(self)
            if url:
                cur = self.composer.input.textCursor()
                # Normalize to GIF if a Giphy MP4 was returned, so it embeds as an image
                try:
                    sel = url
                    low = url.lower()
                    if "giphy.com" in low and low.endswith(".mp4"):
                        sel = url[:-4] + ".gif"
                except Exception:
                    sel = url
                # Insert with surrounding spaces for safety
                cur.insertText((" " if cur.position() else "") + sel + " ")
                self.composer.input.setTextCursor(cur)
                self.composer.input.setFocus()
        except Exception as e:
            try:
                self.toast_host.show_toast(f"GIPHY error: {e}")
            except Exception:
                pass

    def _nick_color(self, nick: str) -> str:
        try:
            s = (nick or "").lower().encode("utf-8")
            h = 0
            for b in s:
                h = (h * 131 + int(b)) & 0xFFFFFFFF
            # map to pleasant hue range, fixed saturation/lightness
            hue = h % 360

            # Convert HSL to RGB (approx) for CSS hex
            def hsl_to_rgb(h, s, light):
                c = (1 - abs(2 * light - 1)) * s
                x = c * (1 - abs(((h / 60) % 2) - 1))
                m = light - c / 2
                if 0 <= h < 60:
                    r, g, b = c, x, 0
                elif 60 <= h < 120:
                    r, g, b = x, c, 0
                elif 120 <= h < 180:
                    r, g, b = 0, c, x
                elif 180 <= h < 240:
                    r, g, b = 0, x, c
                elif 240 <= h < 300:
                    r, g, b = x, 0, c
                else:
                    r, g, b = c, 0, x
                R = int((r + m) * 255)
                G = int((g + m) * 255)
                B = int((b + m) * 255)
                return f"#{R:02x}{G:02x}{B:02x}"

            return hsl_to_rgb(hue, 0.65, 0.6)
        except Exception:
            return "#82b1ff"

    # ----- Chat WebView helpers -----
    def _init_chat_webview(self) -> None:
        try:
            base_html = """
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset=\"utf-8\" />
                <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
                <style>
                :root {
                    color-scheme: dark;
                    --bg1: #0f0f13;
                    --bg2: #141824;
                    --bg3: #0f1220;
                    --fg:  #e0e0e0;
                    --link: #82b1ff;
                }
                body {
                    margin: 0; font-family: -apple-system, Segoe UI, Roboto, Arial, sans-serif;
                    background: linear-gradient(135deg, var(--bg1) 0%, var(--bg2) 50%, var(--bg3) 100%);
                    color: var(--fg);
                }
                #chat { padding: 12px 14px; }
                a { color: var(--link); text-decoration: none; position: relative; }
                a:after { content: ""; position: absolute; left: 0; right: 0; bottom: -2px; height: 2px; background: linear-gradient(90deg, var(--link), #a78bfa); transform: scaleX(0); transition: transform .25s ease; transform-origin: left; }
                a:hover:after { transform: scaleX(1); }
                /* Default media smaller */
                    img, iframe, video { max-width: 320px; border-radius: 10px; box-shadow: 0 6px 20px rgba(0,0,0,.35); transition: transform .2s ease, box-shadow .2s ease; }
                    iframe { border: none; }
                    img:hover, iframe:hover, video:hover { transform: translateY(-2px); box-shadow: 0 10px 28px rgba(0,0,0,.45); }
                    /* Resizable via data-msize */
                    img[data-msize="small"], iframe[data-msize="small"], video[data-msize="small"] { max-width: 320px; }
                    img[data-msize="medium"], iframe[data-msize="medium"], video[data-msize="medium"] { max-width: 560px; }
                    img[data-msize="large"], iframe[data-msize="large"], video[data-msize="large"] { max-width: 800px; }
                    .msg { margin: 8px 0; padding: 6px 8px; border-radius: 8px; background: rgba(255,255,255,0.02); transition: background .2s ease; }
                    .msg:hover { background: rgba(255,255,255,0.05); }
                    .ts { color: #8a8a8a; margin-right: 6px; }
                    .nick { font-weight: 700; color: var(--nick); text-shadow: 0 0 8px color-mix(in oklab, var(--nick) 40%, transparent); }
                    .msg-text { color: #d8d8d8; text-shadow: 0 1px 2px rgba(0,0,0,.45); }
                    /* Simple context menu */
                    #ctx-menu { position: fixed; z-index: 9999; background: #1e1e1e; color: #eee; border: 1px solid #333; border-radius: 8px; padding: 6px; box-shadow: 0 8px 24px rgba(0,0,0,0.6); display: none; }
                    #ctx-menu button { background: transparent; color: #eee; border: none; padding: 8px 12px; text-align: left; width: 100%; cursor: pointer; border-radius: 6px; }
                    #ctx-menu button:hover { background: #2a2a2a; }
                </style>
            </head>
            <body>
                <div id=\"chat\"></div>
                <script>
                function scrollToBottom() {
                    try { window.scrollTo(0, document.body.scrollHeight); } catch (e) {}
                }
                function appendMessage(html) {
                    try {
                        const c = document.getElementById('chat');
                        const d = document.createElement('div');
                        d.className = 'msg';
                        d.innerHTML = html;
                        c.appendChild(d);
                        scrollToBottom();
                    } catch (e) {}
                }
                function startAI() {
                    try {
                        const c = document.getElementById('chat');
                        const d = document.createElement('div');
                        d.className = 'msg';
                        d.innerHTML = '<i>AI:</i> <span id="ai-stream"></span>';
                        c.appendChild(d);
                        scrollToBottom();
                    } catch (e) {}
                }
                function aiChunk(t) {
                    try {
                        const s = document.getElementById('ai-stream');
                        if (s) { s.textContent = (s.textContent || '') + t; scrollToBottom(); }
                    } catch (e) {}
                }
                </script>
            </body>
            </html>
            """
            try:
                # Intercept link clicks so we don't navigate the chat page; route instead
                from PyQt6.QtWebEngineCore import QWebEnginePage

                class _ChatPage(QWebEnginePage):
                    def __init__(self, win):
                        super().__init__(win)
                        self._win = win

                    def javaScriptConsoleMessage(self, level, message, lineNumber, sourceID):
                        try:
                            m = str(message)
                            src = str(sourceID)
                            # Filter common noisy messages
                            noisy = (
                                "requestStorageAccessFor",
                                "generate_204",
                                "googleads.g.doubleclick.net",
                                "CORS policy",
                                "ResizeObserver loop completed",
                            )
                            if any(s in m or s in src for s in noisy):
                                return
                        except Exception:
                            pass
                        try:
                            super().javaScriptConsoleMessage(level, message, lineNumber, sourceID)
                        except Exception:
                            pass

                    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
                        try:
                            # Only intercept user-initiated link clicks
                            if nav_type == QWebEnginePage.NavigationType.NavigationTypeLinkClicked:
                                # Route via main window handler (VideoPanel/BrowserWindow)
                                try:
                                    self._win._on_anchor_clicked(url)
                                except Exception:
                                    pass
                                return False
                        except Exception:
                            pass
                        return super().acceptNavigationRequest(url, nav_type, is_main_frame)

                try:
                    self.chat.setPage(_ChatPage(self))
                except Exception:
                    pass
                self.chat.loadFinished.connect(self._on_chat_loaded)
            except Exception:
                pass
            self.chat.setHtml(base_html, QUrl("about:blank"))
        except Exception:
            pass

    def _apply_chat_theme(self) -> None:
        try:
            palette = self.palette()
            bg1 = palette.color(QPalette.ColorRole.Base).name()
            bg2 = palette.color(QPalette.ColorRole.AlternateBase).name()
            bg3 = palette.color(QPalette.ColorRole.ToolTipBase).name()
            fg = palette.color(QPalette.ColorRole.Text).name()
            link = palette.color(QPalette.ColorRole.Link).name()
            js = f"applyThemeVars({{{'bg1': '{bg1}', 'bg2': '{bg2}', 'bg3': '{bg3}', 'fg': '{fg}', 'link': '{link}'}}})"
            self.chat.page().runJavaScript(js)
        except Exception:
            pass

    def _on_chat_loaded(self, ok: bool) -> None:
        # Mark ready and flush any buffered messages
        self._chat_ready = bool(ok)
        if not self._chat_ready:
            return
        # Apply theme variables to the freshly loaded chat document
        try:
            self._apply_chat_theme()
        except Exception:
            pass
        # Ensure zoom reflects current font size
        try:
            size = int(self._chat_font_size) if self._chat_font_size else None
            if size and size > 0:
                self.chat.setZoomFactor(max(0.6, min(2.0, size / 12.0)))
        except Exception:
            pass
        # Replay scrollback for active channel
        try:
            self._replay_scrollback()
        except Exception:
            pass
        try:
            if self._chat_buf:
                for item in list(self._chat_buf):
                    # If item looks like a raw HTML string, append directly
                    self.chat.page().runJavaScript(f"appendMessage({json.dumps(item)})")
        except Exception:
            pass
        finally:
            try:
                self._chat_buf.clear()
            except Exception:
                pass

    def _chat_append(self, html: str) -> None:
        # Cache into per-channel scrollback first
        try:
            cur = self.bridge.current_channel() or "status"
            buf = self._scrollback.setdefault(cur, [])
            buf.append(html)
            if len(buf) > self._scrollback_limit:
                del buf[: -self._scrollback_limit]
            # Persist to disk best-effort
            self._scrollback_save(cur, buf)
        except Exception:
            pass
        # Then render (or buffer until webview ready)
        try:
            if not getattr(self, "_chat_ready", False):
                getattr(self, "_chat_buf", []).append(html)
                return
            js = f"appendMessage({json.dumps(html)})"
            self.chat.page().runJavaScript(js)
        except Exception:
            pass

    def _replay_scrollback(self, ch: str | None = None) -> None:
        try:
            key = ch or (self.bridge.current_channel() or "status")
            hist = list(self._scrollback.get(key, []))
            if not hist:
                # Attempt to load from disk
                loaded = self._scrollback_load(key)
                if loaded:
                    self._scrollback[key] = list(loaded)
                    hist = list(loaded)
            if not hist:
                return
            # Efficiently append in order
            for h in hist:
                self.chat.page().runJavaScript(f"appendMessage({json.dumps(h)})")
            # Ensure we are at bottom (match base_html helper)
            self.chat.page().runJavaScript("scrollToBottom()")
        except Exception:
            pass

    def _scrollback_path(self, ch: str) -> str | None:
        try:
            base = self._scrollback_dir
            if not base:
                return None
            import os

            os.makedirs(base, exist_ok=True)
            # sanitize filename
            safe = "".join(
                c if c.isalnum() or c in ("#", "-", "_", "@", ".", ":", "+") else "_" for c in ch
            )
            return os.path.join(base, f"scrollback_{safe}.json")
        except Exception:
            return None

    def _scrollback_save(self, ch: str, buf: list[str]) -> None:
        try:
            path = self._scrollback_path(ch)
            if not path:
                return
            import json as _json

            data = buf[-self._scrollback_limit :]
            with open(path, "w", encoding="utf-8") as f:
                _json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass

    def _scrollback_load(self, ch: str) -> list[str] | None:
        try:
            path = self._scrollback_path(ch)
            if not path:
                return None
            import json as _json
            import os

            if not os.path.exists(path):
                return None
            with open(path, encoding="utf-8") as f:
                data = _json.load(f)
            if isinstance(data, list):
                return [str(x) for x in data][-self._scrollback_limit :]
        except Exception:
            pass
        return None

    def _chat_start_ai_line(self) -> None:
        try:
            if not getattr(self, "_chat_ready", False):
                # Represent startAI by an empty AI line to be appended later
                getattr(self, "_chat_buf", []).append("<i>AI:</i> <span id='ai-stream'></span>")
                return
            self.chat.page().runJavaScript("startAI()")
        except Exception:
            pass

    def _chat_ai_chunk(self, text: str) -> None:
        try:
            if not getattr(self, "_chat_ready", False):
                # If AI not ready, accumulate into a synthetic line
                buf = getattr(self, "_chat_buf", None)
                if isinstance(buf, list):
                    buf.append(json.dumps(text))
                return
            self.chat.page().runJavaScript(f"aiChunk({json.dumps(text)})")
        except Exception:
            pass

    def _on_submit(self, text: str) -> None:
        if not text.strip():
            return
        # Send via bridge
        cur = self.bridge.current_channel() or ""
        if cur.startswith("[AI:"):
            # AI session: stream response from Ollama
            try:
                self._chat_append(self._format_message_html("You", text, ts=time.time()))
            except Exception:
                pass
            self._run_ai_inference(cur, text)
        else:
            if text.startswith("/"):
                self._handle_command(text, cur)
            else:
                try:
                    # Use async-safe scheduling
                    self._schedule_async(self.bridge.sendMessage, text)
                    # Local echo only if server does NOT support IRCv3 echo-message
                    do_local_echo = True
                    try:
                        if hasattr(self.bridge, "hasEchoMessage") and self.bridge.hasEchoMessage():
                            do_local_echo = False
                    except Exception:
                        pass
                    if do_local_echo:
                        try:
                            now_ts = time.time()
                            self._chat_append(self._format_message_html("You", text, ts=now_ts))
                            # Record recent outgoing to dedupe server echo
                            try:
                                rec = getattr(self, "_recent_outgoing", {})
                                chan = cur or ""
                                lst = rec.get(chan, [])
                                lst.append((text, now_ts))
                                # keep only last N and within window
                                if len(lst) > 20:
                                    lst = lst[-20:]
                                rec[chan] = lst
                                setattr(self, "_recent_outgoing", rec)
                            except Exception:
                                pass
                        except Exception:
                            pass
                except Exception:
                    # Fallback: raw PRIVMSG to current target
                    if cur:
                        tgt = self._irc_target_from_label(cur)
                        if tgt:
                            self._send_raw(f"PRIVMSG {tgt} :{text}")

    def _default_nick(self) -> str:
        """Generate a randomized default nick (e.g., peach1234)."""
        try:
            import secrets

            return f"peach{secrets.randbelow(9000) + 1000}"
        except Exception:
            import random

            return f"peach{random.randint(1000, 9999)}"

    def _handle_command(self, cmdline: str, cur: str) -> None:
        cmdline = (cmdline or "").strip()
        if not cmdline:
            return
        if not cmdline.startswith("/"):
            return
        parts = cmdline[1:].split(None, 1)
        cmd = parts[0].lower() if parts else ""
        arg = parts[1] if len(parts) > 1 else ""

        def _raw(s: str) -> None:
            self._send_raw(s)

        def _send_to(target: str, msg: str) -> bool:
            fn = getattr(self.bridge, "sendMessageTo", None)
            if callable(fn):
                try:
                    # Bridge slot may be async; schedule safely
                    self._schedule_async(fn, target, msg)
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
            # No local echo here; we'll format on _on_message when echo arrives
        elif cmd in ("join", "j"):
            ch = (arg or "").strip()
            if ch:
                self._join_channel(ch)
        elif cmd == "nick":
            newn = (arg or "").strip()
            if newn:
                self._change_nick(newn)
        elif cmd in ("part", "leave"):
            ch = arg.strip() or cur
            if ch and not ch.startswith(("#", "&")):
                ch = "#" + ch
            if ch:
                try:
                    self.bridge.partChannel(ch)
                except Exception:
                    _raw(f"PART {ch}")
                # Local echo of part
                try:
                    self._chat_append(f"<i>• Left {ch}</i>")
                except Exception:
                    pass
        elif cmd == "msg":
            # /msg <target> <message>
            try:
                target, msg = arg.split(" ", 1)
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
            if arg.startswith("#") and " " in arg:
                ch, topic = arg.split(" ", 1)
            else:
                ch, topic = cur, arg
            ch = (ch or "").strip()
            topic = (topic or "").strip()
            if ch and topic:
                try:
                    self.bridge.setTopic(ch, topic)
                except Exception:
                    _raw(f"TOPIC {ch} :{topic}")
        elif cmd == "mode":
            # /mode <target> <modes>
            try:
                target, modes = arg.split(" ", 1)
            except ValueError:
                return
            target = target.strip()
            modes = modes.strip()
            if not target or not modes:
                return
            try:
                self._schedule_async(self.bridge.setModes, target, modes)
            except Exception:
                _raw(f"MODE {target} {modes}")
        elif cmd == "raw":
            if arg:
                _raw(arg)
        else:
            # Unknown: try as raw
            if arg:
                _raw(parts[0].upper() + " " + arg)
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
            if tok.startswith("#"):
                return tok
        return label

    def _send_raw(self, line: str) -> None:
        sent = False
        for meth in ("sendRaw", "sendCommand"):
            fn = getattr(self.bridge, meth, None)
            if callable(fn):
                try:
                    # Schedule; supports async slots transparently
                    self._schedule_async(fn, line)
                    sent = True
                    break
                except Exception:
                    pass
        if not sent:
            self.toast_host.show_toast("Raw command not supported by bridge")

    def _strip_irc_codes(self, s: str) -> str:
        """Strip common IRC formatting/control codes from text.

        Removes mIRC color codes (\x03[fg][,bg]), bold (\x02), underline (\x1f),
        reverse (\x16), italics (\x1d), and reset (\x0f). Also strips \x04 hex colors.
        """
        if not s:
            return ""
        try:
            # Remove \x04 HEX color (rare): \x04RRGGBB(,RRGGBB)?
            s = re.sub(r"\x04[0-9A-Fa-f]{6}(?:,[0-9A-Fa-f]{6})?", "", s)
            # Remove \x03 color codes like \x0304 or \x0304,02
            s = re.sub(r"\x03(?:\d{1,2}(?:,\d{1,2})?)?", "", s)
            # Remove other simple toggles
            s = s.replace("\x02", "")  # bold
            s = s.replace("\x1f", "")  # underline
            s = s.replace("\x16", "")  # reverse
            s = s.replace("\x1d", "")  # italics
            s = s.replace("\x0f", "")  # reset
            return s
        except Exception:
            return s

    def _on_status(self, s: str) -> None:
        # Feed negotiation parser first with raw line
        try:
            self._negotiate_handle_line(s or "")
        except Exception:
            pass

        # Attempt to extract network prefix and message body
        net = None
        body = s or ""
        try:
            if body.startswith("[") and "]" in body:
                net = body.split("]", 1)[0][1:]
                body = body.split("]", 1)[1].strip()
        except Exception:
            pass

        # Handle raw incoming lines (debug mode provides "<< ...") for inline rendering of numerics (WHOIS, MOTD, LIST, errors, etc.)
        try:
            if body.startswith("<< "):
                raw = body[3:].strip()
                # Parse common WHOIS numerics and related notices
                # Typical: ":server 311 mynick target user host * :Real Name"
                parts = raw.split()
                code = None
                if len(parts) >= 2 and parts[0].startswith(":") and parts[1].isdigit():
                    code = parts[1]
                elif len(parts) >= 1 and parts[0].isdigit():
                    code = parts[0]

                def server_emit(text: str) -> None:
                    """Append a system line to the server view buffer and live UI if that network is selected."""
                    try:
                        if not net:
                            return
                        # Persist as plain text; network select will re-render
                        buf = self._status_by_net.setdefault(net, [])
                        buf.append(text)
                        if len(buf) > 500:
                            del buf[:-500]
                        # Live render if network is selected
                        if getattr(self, "_selected_network", None) == net:
                            html = f"<span class='sys'><i>{self._strip_irc_codes(text)}</i></span>"
                            self.chat.page().runJavaScript(f"appendMessage({json.dumps(html)})")
                    except Exception:
                        pass

                if code in {
                    "311",
                    "312",
                    "317",
                    "318",
                    "319",
                    "330",
                    "671",
                    "313",
                    "338",
                    "301",
                    "005",
                    "375",
                    "372",
                    "376",
                    "422",
                    "321",
                    "322",
                    "323",
                    "433",
                    "471",
                    "473",
                    "474",
                    "475",
                    "401",
                    "402",
                    "404",
                }:
                    try:
                        # Extract target nick if present
                        target_nick = None
                        if len(parts) >= 4 and parts[0].startswith(":"):
                            target_nick = parts[3]
                        # Build readable lines per code
                        if code == "311" and len(parts) >= 7:
                            user = parts[4]
                            host = parts[5]
                            realname = raw.split(":", 2)[-1] if ":" in raw else ""
                            server_emit(f"whois {target_nick}: {user}@{host} — {realname}")
                        elif code == "312" and len(parts) >= 5:
                            server = parts[4]
                            info = raw.split(":", 2)[-1] if ":" in raw else ""
                            server_emit(f"whois {target_nick}: server {server} {info}")
                        elif code == "317" and len(parts) >= 6:
                            idle = parts[4]
                            try:
                                idle_s = int(idle)
                                idle_str = f"idle {idle_s}s"
                            except Exception:
                                idle_str = f"idle {idle}s"
                            server_emit(f"whois {target_nick}: {idle_str}")
                        elif code == "318":
                            server_emit(f"whois {target_nick}: end of WHOIS")
                        elif code == "319":
                            chans = raw.split(":", 2)[-1] if ":" in raw else ""
                            server_emit(f"whois {target_nick}: channels {chans}")
                        elif code == "330" and len(parts) >= 5:
                            account = parts[4]
                            server_emit(f"whois {target_nick}: logged in as {account}")
                        elif code == "671":
                            server_emit(f"whois {target_nick}: secure connection (TLS)")
                        elif code == "313":
                            server_emit(f"whois {target_nick}: is an IRC operator")
                        elif code == "338" and len(parts) >= 5:
                            # 338 RPL_WHOISACTUALLY (real IP), format varies; show trailing text
                            tail = raw.split(":", 2)[-1] if ":" in raw else ""
                            server_emit(f"whois {target_nick}: {tail}")
                        elif code == "301":
                            # RPL_AWAY during WHOIS
                            away = raw.split(":", 2)[-1] if ":" in raw else ""
                            server_emit(f"whois {target_nick}: away — {away}")
                        elif code == "005":
                            # ISUPPORT tokens after nick; until the ':' (trailing) begins
                            # Example: ":server 005 mynick PREFIX=(ov)@+ CHANMODES=beI,k,l,imnpst :are supported by this server"
                            try:
                                # tokens start after parts[2]
                                tokens = []
                                for tok in parts[3:]:
                                    if tok.startswith(":"):
                                        break
                                    tokens.append(tok)
                                mp = self._isupport_by_net.setdefault(net, {})
                                for tok in tokens:
                                    if "=" in tok:
                                        k, v = tok.split("=", 1)
                                        mp[k] = v
                                    else:
                                        mp[tok] = "1"
                                # Display a compact line
                                view = " ".join(tokens[:12]) + (" …" if len(tokens) > 12 else "")
                                server_emit(f"ISUPPORT: {view}")
                            except Exception:
                                pass
                        elif code == "375":
                            server_emit("— MOTD —")
                        elif code == "372":
                            line = raw.split(":", 2)[-1] if ":" in raw else ""
                            server_emit(f"MOTD: {line}")
                        elif code == "376":
                            server_emit("— End of MOTD —")
                        elif code == "422":
                            server_emit("No MOTD available")
                        elif code == "321":
                            server_emit("— LIST: Channel  Users  :Topic —")
                        elif code == "322":
                            # ":server 322 me #chan users :topic"
                            chname = parts[3] if len(parts) > 3 else "?"
                            users = parts[4] if len(parts) > 4 else "?"
                            topic = raw.split(":", 2)[-1] if ":" in raw else ""
                            server_emit(f"LIST {chname}  {users}  :{topic}")
                        elif code == "323":
                            server_emit("— End of LIST —")
                        elif code == "433":
                            bad = parts[3] if len(parts) > 3 else ""
                            server_emit(f"Nick already in use: {bad}")
                        elif code in {"471", "473", "474", "475"}:
                            # Join errors
                            chname = parts[3] if len(parts) > 3 else ""
                            reason = raw.split(":", 2)[-1] if ":" in raw else code
                            server_emit(f"Cannot join {chname}: {reason}")
                        elif code in {"401", "402", "404"}:
                            target = parts[3] if len(parts) > 3 else ""
                            reason = raw.split(":", 2)[-1] if ":" in raw else code
                            server_emit(f"Error {code} {target}: {reason}")
                        # Regardless of handling, return since we've consumed a WHOIS line
                        return
                    except Exception:
                        # Fall through to minimal status handling
                        pass

                # Non-numeric commands (JOIN/PART/QUIT/NICK/TOPIC/MODE) -> channel system messages
                try:
                    # Skip if typed events are wired to avoid duplicates
                    if getattr(self, "_typed_events", False):
                        raise Exception("typed events enabled; skip raw non-numerics")
                    if len(parts) >= 2 and parts[0].startswith(":"):
                        prefix = parts[0][1:]
                        cmd = parts[1].upper()
                        nick = prefix.split("!", 1)[0]

                        def channel_emit(comp: str, text: str) -> None:
                            try:
                                if not comp:
                                    return
                                # Persist to scrollback
                                sb = self._scrollback.setdefault(comp, [])
                                html = (
                                    f"<span class='sys'><i>{self._strip_irc_codes(text)}</i></span>"
                                )
                                sb.append(html)
                                if len(sb) > self._scrollback_limit:
                                    del sb[: -self._scrollback_limit]
                                # Live render if active
                                if (self.bridge.current_channel() or "") == comp:
                                    self.chat.page().runJavaScript(
                                        f"appendMessage({json.dumps(html)})"
                                    )
                                else:
                                    # Increment unread for that channel
                                    try:
                                        self._unread[comp] = self._unread.get(comp, 0) + 1
                                        self.sidebar.set_unread(
                                            comp, self._unread[comp], self._highlights.get(comp, 0)
                                        )
                                    except Exception:
                                        pass
                            except Exception:
                                pass

                        def members_add(comp: str, who: str) -> None:
                            try:
                                names = set(self._names_by_channel.get(comp, []))
                                if who not in names:
                                    names.add(who)
                                    self._names_by_channel[comp] = sorted(names)
                                    if (self.bridge.current_channel() or "") == comp:
                                        self.members.set_members(list(self._names_by_channel[comp]))
                                        self.composer.set_completion_names(
                                            list(self._names_by_channel[comp])
                                        )
                            except Exception:
                                pass

                        def members_remove(comp: str, who: str) -> None:
                            try:
                                names = list(self._names_by_channel.get(comp, []))
                                if who in names:
                                    names = [x for x in names if x != who]
                                    self._names_by_channel[comp] = names
                                    if (self.bridge.current_channel() or "") == comp:
                                        self.members.set_members(list(names))
                                        self.composer.set_completion_names(list(names))
                            except Exception:
                                pass

                        # Determine channel composite label helper
                        def comp_for_chan(chan: str) -> str | None:
                            try:
                                if not net:
                                    return None
                                chn = chan.lstrip(":")
                                return f"{net}:{chn}"
                            except Exception:
                                return None

                        if cmd == "JOIN" and len(parts) >= 3:
                            ch = parts[2]
                            comp = comp_for_chan(ch)
                            if comp:
                                channel_emit(comp, f"• {nick} joined {ch}")
                                members_add(comp, nick)
                            return
                        if cmd == "PART" and len(parts) >= 3:
                            ch = parts[2]
                            reason = raw.split(":", 2)[-1] if ":" in raw else ""
                            comp = comp_for_chan(ch)
                            if comp:
                                txt = (
                                    f"• {nick} left {ch} ({reason})"
                                    if reason
                                    else f"• {nick} left {ch}"
                                )
                                channel_emit(comp, txt)
                                members_remove(comp, nick)
                            return
                        if cmd == "QUIT":
                            reason = raw.split(":", 2)[-1] if ":" in raw else ""
                            # Emit to all channels where nick is present on this net
                            for comp, names in list(self._names_by_channel.items()):
                                if not comp.startswith(f"{net}:"):
                                    continue
                                if nick in names:
                                    txt = (
                                        f"• {nick} quit ({reason})" if reason else f"• {nick} quit"
                                    )
                                    channel_emit(comp, txt)
                                    members_remove(comp, nick)
                            return
                        if cmd == "NICK" and len(parts) >= 3:
                            new_nick = parts[2].lstrip(":")
                            for comp, names in list(self._names_by_channel.items()):
                                if not comp.startswith(f"{net}:"):
                                    continue
                                if nick in names:
                                    channel_emit(comp, f"• {nick} is now known as {new_nick}")
                                    # Update member list
                                    try:
                                        updated = [new_nick if x == nick else x for x in names]
                                        self._names_by_channel[comp] = sorted(set(updated))
                                        if (self.bridge.current_channel() or "") == comp:
                                            self.members.set_members(
                                                list(self._names_by_channel[comp])
                                            )
                                            self.composer.set_completion_names(
                                                list(self._names_by_channel[comp])
                                            )
                                    except Exception:
                                        pass
                            return
                        if cmd == "TOPIC" and len(parts) >= 3:
                            ch = parts[2]
                            topic = raw.split(":", 2)[-1] if ":" in raw else ""
                            comp = comp_for_chan(ch)
                            if comp:
                                channel_emit(comp, f"• {nick} set topic: {topic}")
                            return
                        if cmd == "MODE" and len(parts) >= 4:
                            target = parts[2]
                            modes = " ".join(parts[3:])
                            comp = (
                                comp_for_chan(target)
                                if target.startswith(("#", "&", "+", "!"))
                                else None
                            )
                            if comp:
                                channel_emit(comp, f"• mode/{target} {modes}")
                            else:
                                # user mode or other: emit to server view
                                server_emit(f"mode {target} {modes}")
                            return
                except Exception:
                    pass
        except Exception:
            pass

        # Minimal status verbosity: show only essential connection info
        clean = self._strip_irc_codes(s or "")
        txt = clean.strip()
        if not txt:
            return
        # Filter out raw protocol echoes and noisy lines
        if ">>" in txt:
            return
        # Drop lines that are only a bracketed network prefix like "[net]" or "[net]   "
        if txt.startswith("[") and "]" in txt and not txt.split("]", 1)[1].strip():
            return
        low = txt.lower()
        allowed = (
            ("connecting to " in low)
            or ("connected. registering" in low)
            or ("registering (nick/user sent)" in low)
            or ("001 welcome received" in low)
        )
        if not allowed:
            return
        # Show allowed line in status bar and chat (italic)
        self.status.showMessage(clean, 2500)
        self._chat_append(f"<i>{clean}</i>")

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
        # One-time migration from legacy Peach settings to DeadHop
        try:
            self._maybe_migrate_qsettings()
        except Exception:
            pass
        s = QSettings("DeadHop", "DeadHopClient")
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
                # push to bridge (async)
                try:
                    self._schedule_async(self.bridge.setMonitorList, list(friends))
                except Exception:
                    pass
        except Exception:
            pass
        try:
            avatars = s.value("avatars", {}, type=dict)
            if isinstance(avatars, dict):
                self._avatar_map = dict(avatars)
                # push to widgets
                try:
                    self.friends.set_avatars(self._avatar_map)
                except Exception:
                    pass
                try:
                    self.members.set_avatars(self._avatar_map)
                except Exception:
                    pass
        except Exception:
            pass
        # Presence notification prefs (defaults: online on, offline off)
        try:
            self._notify_presence_online = s.value("notify/presence_online", True, type=bool)
            self._notify_presence_offline = s.value("notify/presence_offline", False, type=bool)
            self._notify_presence_system = s.value("notify/presence_system", True, type=bool)
            self._notify_presence_sound = s.value("notify/presence_sound", False, type=bool)
        except Exception:
            self._notify_presence_online = True
            self._notify_presence_offline = False
            self._notify_presence_system = True
            self._notify_presence_sound = False

    def _save_settings(self) -> None:
        s = QSettings("DeadHop", "DeadHopClient")
        theme = getattr(self, "_current_theme", None)
        if theme:
            s.setValue("theme", theme)
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
            fr = [
                self.friends.list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.friends.list.count())
            ]
            s.setValue("friends", fr)
        except Exception:
            pass
        # avatars
        try:
            s.setValue("avatars", dict(self._avatar_map))
        except Exception:
            pass
        # presence notify prefs
        try:
            s.setValue(
                "notify/presence_online", bool(getattr(self, "_notify_presence_online", True))
            )
            s.setValue(
                "notify/presence_offline", bool(getattr(self, "_notify_presence_offline", False))
            )
            s.setValue(
                "notify/presence_system", bool(getattr(self, "_notify_presence_system", True))
            )
            s.setValue(
                "notify/presence_sound", bool(getattr(self, "_notify_presence_sound", False))
            )
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
        except Exception:
            pass
        finally:
            # Ensure tray icon is hidden and cleaned up on exit
            try:
                if getattr(self, "tray", None) is not None:
                    try:
                        self.tray.hide()
                    except Exception:
                        pass
                    try:
                        self.tray.deleteLater()
                    except Exception:
                        pass
            except Exception:
                pass
            try:
                super().closeEvent(ev)
            except Exception:
                pass

    def _on_tray_activated(self, reason) -> None:
        """Bring the window to front when the tray icon is activated (e.g., clicked)."""
        try:
            # For single-click, double-click, or context. Minimal behavior: show and raise window
            self.showNormal()
            self.raise_()
            try:
                self.activateWindow()
            except Exception:
                pass
        except Exception:
            pass

    def _show_from_tray(self) -> None:
        try:
            self.showNormal()
            self.raise_()
            try:
                self.activateWindow()
            except Exception:
                pass
        except Exception:
            pass

    def _hide_from_tray(self) -> None:
        try:
            self.hide()
        except Exception:
            pass

    def _quit_from_tray(self) -> None:
        try:
            # Ensure proper shutdown path
            self.close()
        except Exception:
            pass

    def _init_quick_toolbar(self) -> None:
        from PyQt6.QtWidgets import (
            QComboBox,
            QFileDialog,
            QInputDialog,
            QSizePolicy,
            QSlider,
        )

        tb = QToolBar("Quick")
        tb.setMovable(False)
        tb.setFloatable(False)
        # Slightly larger icons for readability
        tb.setIconSize(QSize(20, 20))
        # Improve spacing and padding
        try:
            tb.setStyleSheet("QToolBar{padding:4px; spacing:8px;} QLabel{padding:0 2px;}")
        except Exception:
            pass
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)
        # Font size slider
        tb.addWidget(QLabel(" Font "))
        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setMinimum(9)
        sld.setMaximum(22)
        try:
            cur_pt = (
                int(self._chat_font_size) if self._chat_font_size else self.font().pointSize() or 12
            )
        except Exception:
            cur_pt = 12
        sld.setValue(max(9, min(22, int(cur_pt))))
        # Let the slider expand to use available space
        try:
            sld.setMinimumWidth(180)
            sld.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        except Exception:
            pass

        def on_font_changed(val: int) -> None:
            try:
                self._chat_font_size = int(val)
            except Exception:
                self._chat_font_size = 12
            self._apply_global_font_size(int(self._chat_font_size))
            self._save_settings()

        sld.valueChanged.connect(on_font_changed)
        tb.addWidget(sld)

        # Theme dropdown (small set for quick access)
        tb.addSeparator()
        tb.addWidget(QLabel(" Theme "))
        cbo_theme = QComboBox()
        themes: list[str] = []
        try:
            from qt_material import list_themes

            themes = ["Material Dark", "Material Light"] + [
                t for t in list(list_themes()) if t not in ("Material Dark", "Material Light")
            ]
        except Exception:
            themes = ["Material Dark", "Material Light"]
        cbo_theme.addItems(themes)
        if self._current_theme and self._current_theme in themes:
            cbo_theme.setCurrentText(self._current_theme)
        try:
            cbo_theme.setMinimumWidth(160)
            from PyQt6.QtWidgets import QComboBox as _QB

            cbo_theme.setSizeAdjustPolicy(_QB.SizeAdjustPolicy.AdjustToContentsOnFirstShow)
        except Exception:
            pass

        def on_theme(name: str) -> None:
            self._current_theme = name
            try:
                self._apply_qt_material(name)
            except Exception:
                pass
            self._save_settings()

        cbo_theme.currentTextChanged.connect(on_theme)
        tb.addWidget(cbo_theme)

        # Wrap dropdown
        tb.addSeparator()
        tb.addWidget(QLabel(" Wrap "))
        cbo_wrap = QComboBox()
        cbo_wrap.addItems(["On", "Off"])
        cbo_wrap.setCurrentText("On" if self._word_wrap else "Off")
        try:
            cbo_wrap.setMinimumWidth(90)
        except Exception:
            pass

        def on_wrap(txt: str) -> None:
            self._word_wrap = txt == "On"
            self._set_word_wrap(self._word_wrap)
            self._save_settings()

        cbo_wrap.currentTextChanged.connect(on_wrap)
        tb.addWidget(cbo_wrap)

        # Timestamps dropdown
        tb.addSeparator()
        tb.addWidget(QLabel(" Timestamps "))
        cbo_ts = QComboBox()
        cbo_ts.addItems(["Off", "On"])  # default off like settings
        cbo_ts.setCurrentText("On" if self._show_timestamps else "Off")

        def on_ts(txt: str) -> None:
            self._show_timestamps = txt == "On"
            self._set_timestamps(self._show_timestamps)
            self._save_settings()

        cbo_ts.currentTextChanged.connect(on_ts)
        tb.addWidget(cbo_ts)

        # Join channel quick control
        tb.addSeparator()
        tb.addWidget(QLabel(" Join "))
        join_box = QLineEdit()
        join_box.setPlaceholderText("#channel")
        join_box.setFixedWidth(140)

        def do_join():
            ch = join_box.text().strip()
            if ch:
                self._join_channel(ch)
                join_box.clear()

        join_box.returnPressed.connect(do_join)
        tb.addWidget(join_box)
        btn_join = QPushButton("+")
        btn_join.setFixedWidth(22)
        btn_join.clicked.connect(do_join)
        tb.addWidget(btn_join)

        # Change nick quick control (button opens prompt)
        tb.addSeparator()
        btn_nick = QPushButton("Nick…")

        def on_nick():
            try:
                cur_nick = ""  # we may not have it; allow blank
                new, ok = QInputDialog.getText(self, "Change Nick", "New nickname:", text=cur_nick)
                if ok and new.strip():
                    self._change_nick(new.strip())
            except Exception:
                pass

        btn_nick.clicked.connect(on_nick)
        tb.addWidget(btn_nick)

        # Quick user mode toggles (+i, -i, +x, -x)
        tb.addSeparator()
        tb.addWidget(QLabel(" Me "))
        btn_ui = QPushButton("+i")
        btn_ux = QPushButton("+x")
        btn_di = QPushButton("-i")
        btn_dx = QPushButton("-x")
        btn_ui.setFixedWidth(28)
        btn_ux.setFixedWidth(28)
        btn_di.setFixedWidth(28)
        btn_dx.setFixedWidth(28)
        try:
            btn_ui.clicked.connect(lambda: self.bridge.setMyModes("+i"))
            btn_di.clicked.connect(lambda: self.bridge.setMyModes("-i"))
            btn_ux.clicked.connect(lambda: self.bridge.setMyModes("+x"))
            btn_dx.clicked.connect(lambda: self.bridge.setMyModes("-x"))
        except Exception:
            pass
        tb.addWidget(btn_ui)
        tb.addWidget(btn_di)
        tb.addWidget(btn_ux)
        tb.addWidget(btn_dx)

        # Notifications toggles
        tb.addSeparator()
        tb.addWidget(QLabel(" Notify "))
        chk_toast = QCheckBox("Toast")
        chk_tray = QCheckBox("Tray")
        chk_sound = QCheckBox("Sound")
        chk_toast.setChecked(getattr(self, "_notify_toast", True))
        chk_tray.setChecked(getattr(self, "_notify_tray", True))
        chk_sound.setChecked(getattr(self, "_notify_sound", True))

        def on_toast(v: bool) -> None:
            self._notify_toast = bool(v)
            try:
                s = QSettings("DeadHop", "DeadHopClient")
                s.setValue("notify/toast", bool(v))
            except Exception:
                pass

        def on_tray(v: bool) -> None:
            self._notify_tray = bool(v)
            try:
                s = QSettings("DeadHop", "DeadHopClient")
                s.setValue("notify/tray", bool(v))
            except Exception:
                pass

        def on_sound(v: bool) -> None:
            self._notify_sound = bool(v)
            try:
                s = QSettings("DeadHop", "DeadHopClient")
                s.setValue("notify/sound", bool(v))
            except Exception:
                pass

        chk_toast.toggled.connect(on_toast)
        chk_tray.toggled.connect(on_tray)
        chk_sound.toggled.connect(on_sound)
        tb.addWidget(chk_toast)
        tb.addWidget(chk_tray)
        tb.addWidget(chk_sound)

        # Sound pickers (message/highlight) and volume
        try:
            tb.addWidget(QLabel(" Msg "))
            btn_msg = QPushButton("Pick…")

            def pick_msg() -> None:
                try:
                    fn, _ = QFileDialog.getOpenFileName(
                        self, "Choose Message Sound", filter="Sounds (*.wav *.ogg)"
                    )
                    if fn:
                        from PyQt6.QtCore import QUrl

                        (
                            self._se_msg.setSource(QUrl.fromLocalFile(fn))
                            if getattr(self, "_se_msg", None)
                            else None
                        )
                        s = QSettings("DeadHop", "DeadHopClient")
                        s.setValue("notify/sound_msg", fn)
                except Exception:
                    pass

            btn_msg.clicked.connect(pick_msg)
            tb.addWidget(btn_msg)

            tb.addWidget(QLabel(" HL "))
            btn_hl = QPushButton("Pick…")

            def pick_hl() -> None:
                try:
                    fn, _ = QFileDialog.getOpenFileName(
                        self, "Choose Highlight Sound", filter="Sounds (*.wav *.ogg)"
                    )
                    if fn:
                        from PyQt6.QtCore import QUrl

                        (
                            self._se_hl.setSource(QUrl.fromLocalFile(fn))
                            if getattr(self, "_se_hl", None)
                            else None
                        )
                        s = QSettings("DeadHop", "DeadHopClient")
                        s.setValue("notify/sound_hl", fn)
                except Exception:
                    pass

            btn_hl.clicked.connect(pick_hl)
            tb.addWidget(btn_hl)

            tb.addWidget(QLabel(" Friend "))
            btn_pr = QPushButton("Pick…")

            def pick_pr() -> None:
                try:
                    fn, _ = QFileDialog.getOpenFileName(
                        self, "Choose Friend Online Sound", filter="Sounds (*.wav *.ogg)"
                    )
                    if fn:
                        from PyQt6.QtCore import QUrl

                        (
                            self._se_presence.setSource(QUrl.fromLocalFile(fn))
                            if getattr(self, "_se_presence", None)
                            else None
                        )
                        s = QSettings("DeadHop", "DeadHopClient")
                        s.setValue("notify/sound_presence", fn)
                except Exception:
                    pass

            btn_pr.clicked.connect(pick_pr)
            tb.addWidget(btn_pr)

            # Toggle for friend-online sound
            try:
                chk_pr = QCheckBox("Friend sound")
                chk_pr.setChecked(bool(getattr(self, "_notify_presence_sound", False)))

                def on_pr(v: bool) -> None:
                    try:
                        self._notify_presence_sound = bool(v)
                        s = QSettings("DeadHop", "DeadHopClient")
                        s.setValue("notify/presence_sound", bool(v))
                    except Exception:
                        pass

                chk_pr.toggled.connect(on_pr)
                tb.addWidget(chk_pr)
            except Exception:
                pass

            tb.addWidget(QLabel(" Vol "))
            s_vol = QSlider(Qt.Orientation.Horizontal)
            s_vol.setMinimum(0)
            s_vol.setMaximum(100)
            try:
                s = QSettings("DeadHop", "DeadHopClient")
                cur = float(s.value("notify/sound_volume", 0.7))
            except Exception:
                cur = 0.7
            s_vol.setValue(int(cur * 100))

            def on_vol(v: int) -> None:
                try:
                    vol = max(0.0, min(1.0, v / 100.0))
                    if getattr(self, "_se_msg", None):
                        try:
                            self._se_msg.setVolume(vol)
                        except Exception:
                            pass
                    if getattr(self, "_se_hl", None):
                        try:
                            self._se_hl.setVolume(vol)
                        except Exception:
                            pass
                    if getattr(self, "_se_presence", None):
                        try:
                            self._se_presence.setVolume(vol)
                        except Exception:
                            pass
                    s = QSettings("DeadHop", "DeadHopClient")
                    s.setValue("notify/sound_volume", float(vol))
                except Exception:
                    pass

            s_vol.valueChanged.connect(on_vol)
            s_vol.setFixedWidth(100)
            tb.addWidget(s_vol)
        except Exception:
            pass

    def _init_notifications(self) -> None:
        """Initialize tray icon and sound effects (best-effort)."""
        # System tray icon for popups
        try:
            if not hasattr(self, "tray"):
                self.tray = QSystemTrayIcon(self)
                # Ensure a valid icon is set to avoid warnings
                icon = self.windowIcon()
                try:
                    if icon.isNull():
                        from PyQt6.QtWidgets import QStyle

                        icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
                        self.setWindowIcon(icon)
                except Exception:
                    pass
                self.tray.setIcon(icon)
                self.tray.setToolTip("DeadHop")
                self.tray.setVisible(True)
        except Exception:
            pass
        # Sounds (best-effort); use QSoundEffect if available, else fallback to beep
        self._se_msg = None
        self._se_hl = None
        try:
            from PyQt6.QtMultimedia import QSoundEffect

            base = Path(__file__).resolve().parents[1] / "resources" / "sounds"
            msg = base / "message.wav"
            hl = base / "highlight.wav"
            if msg.exists():
                self._se_msg = QSoundEffect(self)
                self._se_msg.setSource(QUrl.fromLocalFile(str(msg)))
                self._se_msg.setVolume(0.25)
            if hl.exists():
                self._se_hl = QSoundEffect(self)
                self._se_hl.setSource(QUrl.fromLocalFile(str(hl)))
                self._se_hl.setVolume(0.35)
        except Exception:
            self._se_msg = None
            self._se_hl = None

    def _notify_event(self, title: str, body: str, highlight: bool = False) -> None:
        """Emit toast, tray popup, and sound based on preferences."""
        # Toast
        try:
            if self._notify_toast:
                self.toast_host.show_toast(f"{title}: {body}")
        except Exception:
            pass
        # Tray popup
        try:
            if self._notify_tray and hasattr(self, "tray") and self.tray:
                self.tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 3500)
        except Exception:
            pass
        # Sound
        try:
            if self._notify_sound:
                se = self._se_hl if highlight and self._se_hl else self._se_msg
                if se:
                    se.play()
                else:
                    from PyQt6.QtWidgets import QApplication

                    QApplication.beep()
        except Exception:
            pass

    def _join_channel(self, ch: str) -> None:
        ch = ch.strip()
        if not ch:
            return
        # Ensure channel starts with '#'
        if not (
            ch.startswith("#") or ch.startswith("&") or ch.startswith("+") or ch.startswith("!")
        ):
            ch = "#" + ch
        # Determine target network from current channel or selected network in the tree
        composite = None
        try:
            cur = self.bridge.current_channel() or ""
            net = None
            if cur and ":" in cur and not cur.startswith("["):
                net = cur.split(":", 1)[0]
            if not net:
                net = getattr(self, "_selected_network", None)
            if net:
                composite = f"{net}:{ch}"
        except Exception:
            pass
        try:
            fn = getattr(self.bridge, "joinChannel", None)
            if callable(fn) and composite:
                self._schedule_async(fn, composite)
                return
        except Exception:
            pass
        # Fallback raw (will hit all networks if none selected)
        self._send_raw(f"JOIN {ch}")

    def _change_nick(self, nick: str) -> None:
        nick = (nick or "").strip()
        if not nick:
            return
        # Prefer raw NICK (works on all networks)
        self._send_raw(f"NICK {nick}")

    def _apply_global_font_size(self, pt: int) -> None:
        # Apply to entire app via QApplication font, plus chat zoom
        try:
            app = QApplication.instance()
            if app is not None:
                f = app.font()
                if pt > 0:
                    f.setPointSize(int(pt))
                    app.setFont(f)
        except Exception:
            pass
        # Chat webview: use zoom factor so content scales
        try:
            new_zoom = max(0.6, min(2.0, pt / 12.0))
            if getattr(self, "_last_zoom", None) != new_zoom:
                self.chat.setZoomFactor(new_zoom)
                self._last_zoom = new_zoom
        except Exception:
            pass
        # No closeEvent calls here; just return after applying font/zoom

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
        # Also apply global font size to the app and chat zoom
        try:
            if self._chat_font_size and int(self._chat_font_size) > 0:
                self._apply_global_font_size(int(self._chat_font_size))
        except Exception:
            pass
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
        # Load current autoconnect flag and notification settings
        auto = False
        notify_toast = True
        notify_tray = True
        notify_sound = True
        presence_sound_enabled = False
        sound_msg_path = None
        sound_hl_path = None
        sound_presence_path = None
        sound_volume = 0.7
        try:
            s = QSettings("DeadHop", "DeadHopClient")
            # Default to autoconnect enabled
            auto = s.value("server/autoconnect", True, type=bool)
            notify_toast = bool(s.value("notify/toast", getattr(self, "_notify_toast", True)))
            notify_tray = bool(s.value("notify/tray", getattr(self, "_notify_tray", True)))
            notify_sound = bool(s.value("notify/sound", getattr(self, "_notify_sound", True)))
            presence_sound_enabled = bool(
                s.value("notify/presence_sound", getattr(self, "_notify_presence_sound", False))
            )
            sound_msg_path = s.value("notify/sound_msg", "", type=str) or None
            sound_hl_path = s.value("notify/sound_hl", "", type=str) or None
            sound_presence_path = s.value("notify/sound_presence", "", type=str) or None
            try:
                sound_volume = float(s.value("notify/sound_volume", 0.7))
            except Exception:
                sound_volume = 0.7
        except Exception:
            pass
        dlg = SettingsDialog(
            self,
            theme_options=theme_options,
            current_theme=self._current_theme,
            opacity=float(self.windowOpacity()),
            font_family=fam,
            font_point_size=pt,
            highlight_words=self._highlight_keywords,
            friends=[
                self.friends.list.item(i).data(Qt.ItemDataRole.UserRole)
                for i in range(self.friends.list.count())
            ],
            word_wrap=self._word_wrap,
            show_timestamps=self._show_timestamps,
            autoconnect=auto,
            auto_negotiate=bool(getattr(self, "_auto_negotiate", True)),
            prefer_tls=bool(getattr(self, "_prefer_tls", True)),
            try_starttls=bool(getattr(self, "_try_starttls", False)),
            # Sounds tab
            notify_toast=bool(notify_toast),
            notify_tray=bool(notify_tray),
            notify_sound=bool(notify_sound),
            presence_sound_enabled=bool(presence_sound_enabled),
            sound_msg_path=sound_msg_path,
            sound_hl_path=sound_hl_path,
            sound_presence_path=sound_presence_path,
            sound_volume=float(sound_volume),
        )
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
            try:
                self._schedule_async(self.bridge.setMonitorList, fr)
            except Exception:
                pass
            # Network prefs
            try:
                self._auto_negotiate = dlg.selected_auto_negotiate()
                self._prefer_tls = dlg.selected_prefer_tls()
                # Optional STARTTLS attempt preference
                if hasattr(dlg, "selected_try_starttls"):
                    self._try_starttls = dlg.selected_try_starttls()
            except Exception:
                pass
            # Persist
        try:
            # Save autoconnect flag only (server details saved via Connect dialog)
            s = QSettings("DeadHop", "DeadHopClient")
            s.setValue("server/autoconnect", dlg.selected_autoconnect())
        except Exception:
            pass
        self._save_settings()

    # ---- Server persistence / autoconnect ----
    def _save_server_settings(
        self,
        host: str,
        port: int,
        tls: bool,
        nick: str,
        user: str,
        realname: str,
        channels: list[str],
        autoconnect: bool,
        password: str | None,
        sasl_user: str | None,
    ) -> None:
        try:
            s = QSettings("DeadHop", "DeadHopClient")
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
            s = QSettings("DeadHop", "DeadHopClient")
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
                return (
                    host,
                    int(port),
                    bool(tls),
                    nick,
                    user or "deadhop",
                    realname or "DeadHop",
                    list(channels),
                    password,
                    sasl_user,
                    bool(autoconnect),
                )
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
            self._schedule_async(
                self.bridge.connectHost,
                host,
                port,
                tls,
                nick,
                user,
                realname,
                channels,
                password,
                sasl_user,
                bool(ignore),
            )
            if getattr(self, "_auto_negotiate", True):
                # Best-effort: kick off negotiation shortly after connect
                self._schedule_async(
                    self._negotiate_on_connect, host, nick, user, password, sasl_user
                )
            self.status.showMessage(f"Auto-connecting to {host}:{port}…", 2000)
            self._my_nick = nick
        except Exception:
            try:
                self.bridge.connectHost(
                    host,
                    port,
                    tls,
                    nick,
                    user,
                    realname,
                    channels,
                    password,
                    sasl_user,
                    bool(ignore),
                )
                if getattr(self, "_auto_negotiate", True):
                    self._schedule_async(
                        self._negotiate_on_connect, host, nick, user, password, sasl_user
                    )
            except Exception:
                pass

    def _set_word_wrap(self, en: bool) -> None:
        self._word_wrap = bool(en)
        self._init_chat_webview()
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
        # Reset the chat document
        self._init_chat_webview()

    def _on_channels_updated(self, labels: list[str]) -> None:
        """Keep sidebar tree in sync with bridge channel list."""
        try:
            self._channel_labels = list(labels or [])
            self.sidebar.set_channels(self._channel_labels)
        except Exception:
            pass
        # Ensure current channel remains valid
        try:
            cur = self.bridge.current_channel() or ""
            if cur and cur not in (self._channel_labels or []):
                self.bridge.set_current_channel(
                    self._channel_labels[0] if self._channel_labels else ""
                )
        except Exception:
            pass

    def _on_channel_action(self, ch: str, action: str) -> None:
        action = (action or "").strip().lower()
        ch = ch or ""
        if not ch:
            return
        if action == "open log":
            try:
                self._open_logs_folder()
            except Exception:
                pass
            return
        if action in ("join",):
            try:
                self._schedule_async(self.bridge.joinChannel, ch)
            except Exception:
                pass
            return
        if action in ("part", "close"):
            if ch.startswith("[AI:"):
                try:
                    if not hasattr(self, "_channel_labels"):
                        self._channel_labels = []
                    if ch in self._channel_labels:
                        self._channel_labels.remove(ch)
                        self.sidebar.set_channels(self._channel_labels)
                except Exception:
                    pass
                # select a remaining channel if needed
                try:
                    cur = self.bridge.current_channel() or ""
                    if cur == ch:
                        self.bridge.set_current_channel(
                            self._channel_labels[0] if self._channel_labels else ""
                        )
                except Exception:
                    pass
            else:
                try:
                    self._schedule_async(self.bridge.partChannel, ch)
                except Exception:
                    pass
            return
        if action == "topic":
            try:
                txt, ok = QInputDialog.getText(self, "Set Topic", f"New topic for {ch}:", text="")
                if ok:
                    self._schedule_async(self.bridge.setTopic, ch, txt)
            except Exception:
                pass
            return
        if action == "modes":
            try:
                txt, ok = QInputDialog.getText(
                    self, "Set Modes", f"Channel modes for {ch} (e.g. +i or +k key):", text=""
                )
                if ok and txt.strip():
                    self._schedule_async(self.bridge.setModes, ch, txt.strip())
            except Exception:
                pass
            return

    def _on_network_action(self, net: str, action: str) -> None:
        action = (action or "").strip().lower()
        if action == "disconnect" and net:
            try:
                self._schedule_async(self.bridge.disconnectNetwork, net)
            except Exception:
                pass

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
            try:
                self._send_raw(f"WHOIS {nick}")
            except Exception:
                try:
                    self._chat_append(f"<i>WHOIS {nick} (not sent: no raw command API)</i>")
                except Exception:
                    pass
        elif action == "query":
            label = f"[PM:{nick}]"
            try:
                # Add PM tab without collapsing existing server trees
                if label not in self._channel_labels:
                    self._channel_labels.append(label)
                self.sidebar.set_channels(self._channel_labels)
                self.sidebar.set_unread(label, 0, 0)
            except Exception:
                pass
            self.bridge.set_current_channel(label)
        elif action == "kick":
            ch = self.bridge.current_channel() or ""
            reason, ok = QInputDialog.getText(
                self, "Kick", f"Reason for kicking {nick} from {ch}:", text=""
            )
            if ok:
                sent = False
                for meth, cmd in (
                    ("kickUser", None),
                    ("sendRaw", f"KICK {ch} {nick} :{reason}"),
                    ("sendCommand", f"KICK {ch} {nick} :{reason}"),
                ):
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
            mask, ok = QInputDialog.getText(
                self, "Ban", f"Ban mask or nick for {ch} (e.g. {nick} or *!*@host):", text=nick
            )
            if ok and mask.strip():
                sent = False
                for meth, cmd in (
                    ("setModes", None),
                    ("sendRaw", f"MODE {ch} +b {mask}"),
                    ("sendCommand", f"MODE {ch} +b {mask}"),
                ):
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
            for meth, cmd in (
                ("setModes", None),
                ("sendRaw", f"MODE {ch} +o {nick}"),
                ("sendCommand", f"MODE {ch} +o {nick}"),
            ):
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
            for meth, cmd in (
                ("setModes", None),
                ("sendRaw", f"MODE {ch} -o {nick}"),
                ("sendCommand", f"MODE {ch} -o {nick}"),
            ):
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
        try:
            from PyQt6.QtWebEngineCore import QWebEnginePage

            flags = QWebEnginePage.FindFlag(0)
            if not forward:
                flags = QWebEnginePage.FindFlag.FindBackward
            self.chat.page().findText(pattern, flags)
        except Exception:
            pass

    # ----- Theme helpers -----
    def _apply_theme(self, name: str) -> None:
        if _theme_manager is None:
            return
        tm = _theme_manager()
        tm.set_theme(name)
        tm.apply()
        self._current_theme = name
        self._sync_theme_actions()
        # Sync chat view colors with current palette
        try:
            self._apply_chat_theme()
        except Exception:
            pass

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
                        base[:-5]
                    candidates.extend(
                        [
                            f"{base}.xml",
                            f"{base}_dark.xml",
                            f"{base}_light.xml",
                            f"dark_{base}.xml",
                            f"light_{base}.xml",
                        ]
                    )
                    chosen = next((c for c in candidates if c in themes), None)
                if not chosen:
                    chosen = (
                        "dark_teal.xml"
                        if "dark_teal.xml" in themes
                        else (themes[0] if themes else None)
                    )
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
            # Push palette-derived colors into chat webview
            try:
                self._apply_chat_theme()
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
        text, ok = QInputDialog.getText(
            self, "Highlight Words", "Comma-separated keywords:", text=cur
        )
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
            try:
                msg = text or ""
                # Deduplicate against our optimistic local echo: if the server echoes
                # our own message shortly after we sent it, skip rendering it again.
                try:
                    if self._my_nick and nick and nick.lower() == self._my_nick.lower():
                        rec = getattr(self, "_recent_outgoing", {})
                        lst = rec.get(target, [])
                        if lst:
                            # consider duplicates if same text within 5s
                            cutoff = ts - 5.0
                            # prune old
                            lst = [(t, tts) for (t, tts) in lst if tts >= cutoff]
                            rec[target] = lst
                            setattr(self, "_recent_outgoing", rec)
                            for t, _tts in lst:
                                if t == msg:
                                    return
                except Exception:
                    pass
                # CTCP ACTION formatting: \x01ACTION ...\x01 -> "* nick ..."
                if msg.startswith("\x01ACTION ") and msg.endswith("\x01"):
                    act = msg[len("\x01ACTION ") : -1].strip()
                    rendered = self._format_message_html(nick, f"* {act}", ts)
                else:
                    rendered = self._format_message_html(nick, self._strip_irc_codes(msg), ts)
                self._chat_append(rendered)
            except Exception:
                pass
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
            low = (text or "").lower()
            if self._my_nick and self._my_nick.lower() in low:
                hl = True
            else:
                for w in self._highlight_keywords:
                    if w.lower() in low:
                        hl = True
                        break
            if hl:
                # mark highlight specially (could style badge differently)
                self._highlights[target] = self._highlights.get(target, 0) + 1
                # Notification on highlight
                try:
                    ch = target.split(":", 1)[-1]
                    self._notify_event(
                        f"Mention in {ch}", f"{nick}: {self._strip_irc_codes(text)}", highlight=True
                    )
                except Exception:
                    pass
            else:
                # Non-highlight unread notification (only when not current)
                if target != cur:
                    try:
                        ch = target.split(":", 1)[-1]
                        self._notify_event(
                            f"New message in {ch}",
                            f"{nick}: {self._strip_irc_codes(text)}",
                            highlight=False,
                        )
                    except Exception:
                        pass
                # Centralized notifications
                try:
                    self._notify_event(f"Highlight in {target}", f"{nick}: {text}", True)
                except Exception:
                    pass
                # update sidebar labels
                try:
                    self.sidebar.set_unread(
                        target, self._unread.get(target, 0), self._highlights.get(target, 0)
                    )
                except Exception:
                    pass
        # Logging
        try:
            self.logger.append("irc", target or cur or "status", f"<{nick}> {text}", ts)
        except Exception:
            pass

    def _on_status(self, s: str) -> None:
        # Expect format like "[net] message"; persist and show when that network is selected in the server tree
        try:
            net = None
            msg = s or ""
            if msg.startswith("[") and "]" in msg:
                net = msg.split("]", 1)[0][1:]
                msg = msg.split("]", 1)[1].strip()
            if not net:
                return
            # Persist raw status lines per-network
            buf = self._status_by_net.setdefault(net, [])
            buf.append(msg)
            if len(buf) > 500:
                del buf[:-500]
            # If the network (top item) is currently selected, render live
            try:
                if getattr(self, "_selected_network", None) == net:
                    html = f"<span class='sys'><i>{self._strip_irc_codes(msg)}</i></span>"
                    self.chat.page().runJavaScript(f"appendMessage({json.dumps(html)})")
            except Exception:
                pass
        except Exception:
            pass

    def _on_network_selected(self, net: str) -> None:
        try:
            # Mark selected network and clear channel selection context
            self._selected_network = net
            # Show just the server name when no channel is selected
            self.members.set_members([net])
            try:
                self.members.title.setText("Server")
            except Exception:
                pass
            # Clear chat view and replay server status buffer for this net
            try:
                self.chat.page().runJavaScript(
                    "(function(){var c=document.getElementById('chat'); if(c) c.innerHTML='';})();"
                )
            except Exception:
                pass
            try:
                lines = list(self._status_by_net.get(net, []))
                for m in lines:
                    html = f"<span class='sys'><i>{self._strip_irc_codes(m)}</i></span>"
                    self.chat.page().runJavaScript(f"appendMessage({json.dumps(html)})")
            except Exception:
                pass
        except Exception:
            pass

    def _on_names(self, channel: str, names: list[str]) -> None:
        # Merge incremental updates into cache keyed by channel label
        try:
            existing = set(self._names_by_channel.get(channel, []))
            incoming = set(names or [])
            merged = sorted(existing.union(incoming))
            self._names_by_channel[channel] = merged
        except Exception:
            # Fallback: replace cache
            self._names_by_channel[channel] = list(names or [])
        # Only update the visible list if this channel is the active one
        cur = self.bridge.current_channel()
        if cur and channel == cur:
            current = self._names_by_channel.get(channel, list(names or []))
            self.members.set_members(list(current))
            # Provide names to composer for tab completion
            try:
                self.composer.set_completion_names(list(current))
            except Exception:
                pass

    # ----- Typed IRC event handlers (JOIN/PART/QUIT/NICK/TOPIC/MODE) -----
    def _channel_emit(self, comp: str, text: str) -> None:
        try:
            if not comp:
                return
            sb = self._scrollback.setdefault(comp, [])
            html = f"<span class='sys'><i>{self._strip_irc_codes(text)}</i></span>"
            sb.append(html)
            if len(sb) > self._scrollback_limit:
                del sb[: -self._scrollback_limit]
            if (self.bridge.current_channel() or "") == comp:
                self.chat.page().runJavaScript(f"appendMessage({json.dumps(html)})")
            else:
                # bump unread
                try:
                    self._unread[comp] = self._unread.get(comp, 0) + 1
                    self.sidebar.set_unread(comp, self._unread[comp], self._highlights.get(comp, 0))
                except Exception:
                    pass
        except Exception:
            pass

    def _members_add(self, comp: str, who: str) -> None:
        try:
            names = set(self._names_by_channel.get(comp, []))
            if who not in names:
                names.add(who)
                self._names_by_channel[comp] = sorted(names)
                if (self.bridge.current_channel() or "") == comp:
                    self.members.set_members(list(self._names_by_channel[comp]))
                    self.composer.set_completion_names(list(self._names_by_channel[comp]))
        except Exception:
            pass

    def _members_remove(self, comp: str, who: str) -> None:
        try:
            names = list(self._names_by_channel.get(comp, []))
            if who in names:
                names = [x for x in names if x != who]
                self._names_by_channel[comp] = names
                if (self.bridge.current_channel() or "") == comp:
                    self.members.set_members(list(names))
                    self.composer.set_completion_names(list(names))
        except Exception:
            pass

    def _on_user_joined(self, comp: str, nick: str) -> None:
        ch = comp.split(":", 1)[1] if ":" in comp else comp
        self._channel_emit(comp, f"• {nick} joined {ch}")
        self._members_add(comp, nick)

    def _on_user_parted(self, comp: str, nick: str) -> None:
        ch = comp.split(":", 1)[1] if ":" in comp else comp
        self._channel_emit(comp, f"• {nick} left {ch}")
        self._members_remove(comp, nick)

    def _on_user_quit(self, net: str, nick: str) -> None:
        try:
            for comp, names in list(self._names_by_channel.items()):
                if not comp.startswith(f"{net}:"):
                    continue
                if nick in names:
                    self._channel_emit(comp, f"• {nick} quit")
                    self._members_remove(comp, nick)
        except Exception:
            pass

    def _on_user_nick_changed(self, net: str, old: str, new: str) -> None:
        try:
            for comp, names in list(self._names_by_channel.items()):
                if not comp.startswith(f"{net}:"):
                    continue
                if old in names:
                    self._channel_emit(comp, f"• {old} is now known as {new}")
                    updated = [new if x == old else x for x in names]
                    self._names_by_channel[comp] = sorted(set(updated))
                    if (self.bridge.current_channel() or "") == comp:
                        self.members.set_members(list(self._names_by_channel[comp]))
                        self.composer.set_completion_names(list(self._names_by_channel[comp]))
        except Exception:
            pass

    def _on_channel_topic(self, comp: str, actor: str, topic: str) -> None:
        self._channel_emit(comp, f"• {actor} set topic: {topic}")

    def _on_channel_mode(self, comp: str, actor: str, modes: str) -> None:
        ch = comp.split(":", 1)[1] if ":" in comp else comp
        self._channel_emit(comp, f"• mode/{ch} {modes}")

    def _on_channel_mode_users(self, comp: str, changes: list) -> None:
        # Summarize user mode changes, e.g., +o nick, -v nick
        try:
            parts = []
            for add, mode, nick in changes:
                sign = "+" if add else "-"
                parts.append(f"{sign}{mode} {nick}")
            if parts:
                ch = comp.split(":", 1)[1] if ":" in comp else comp
                self._channel_emit(comp, f"• mode/{ch} " + " ".join(parts))
        except Exception:
            pass

    def _on_channel_clicked(self, ch: str) -> None:
        if ch:
            # If user clicks the same channel after selecting the server node,
            # BridgeQt may suppress the signal (no change). Force a refresh.
            cur = self.bridge.current_channel()
            self.bridge.set_current_channel(ch)
            if ch == cur:
                # Manually trigger population of members/composer and sidebar state
                self._on_current_channel_changed(ch)

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
            self._schedule_async(
                self.bridge.connectHost,
                "irc.libera.chat",
                6697,
                True,
                nick,
                "deadhop",
                "DeadHop",
                channels,
                None,
                None,
                False,
            )
        except Exception:
            try:
                import random

                nick = f"DeadRabbit{random.randint(1000, 9999)}"
                self.bridge.connectHost(
                    "irc.anonops.com",
                    6697,
                    True,
                    nick,
                    "deadhop",
                    "DeadHop",
                    channels,
                    None,
                    None,
                    False,
                )
            except Exception:
                pass

    def _open_connect_dialog(self) -> None:
        dlg = ConnectDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            vals = dlg.values()
            # Unpack new signature with remember/autoconnect
            (
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
            ) = vals
            # Harden: normalize host before resolving policy
            host = self._normalize_host(host)
            host, port, tls = self._resolve_connect_policy(host, port, tls)
            if not nick:
                nick = self._default_nick()
            # Persist if requested
            if remember:
                self._save_server_settings(
                    host,
                    port,
                    tls,
                    nick,
                    user,
                    realname,
                    chans,
                    bool(autoconnect),
                    password,
                    sasl_user,
                )
                # Also save into multi-server store with a name
                name, ok = QInputDialog.getText(
                    self, "Save Server", "Enter a name for this server:", text=f"{host}:{port}"
                )
                if ok and name.strip():
                    self._servers_save(
                        name.strip(),
                        host,
                        port,
                        tls,
                        nick,
                        user,
                        realname,
                        chans,
                        bool(autoconnect),
                        password,
                        sasl_user,
                    )
            # Fire and forget: async slot
            try:
                self._schedule_async(
                    self.bridge.connectHost,
                    host,
                    port,
                    tls,
                    nick,
                    user,
                    realname,
                    chans,
                    password,
                    sasl_user,
                    False,
                )
                if getattr(self, "_auto_negotiate", True):
                    self._schedule_async(
                        self._negotiate_on_connect, host, nick, user, password, sasl_user
                    )
            except Exception:
                # Fallback: direct call if bridge is sync in this build
                try:
                    self.bridge.connectHost(
                        host, port, tls, nick, user, realname, chans, password, sasl_user, False
                    )
                    if getattr(self, "_auto_negotiate", True):
                        self._schedule_async(
                            self._negotiate_on_connect, host, nick, user, password, sasl_user
                        )
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
                    h = h[len(pref) :]
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

    def _negotiate_on_connect(
        self,
        host: str,
        nick: str | None,
        user: str | None,
        password: str | None,
        sasl_user: str | None,
    ) -> None:
        """Minimal IRCv3 CAP and optional SASL negotiation.

        Best-effort via raw commands; safe to call even if server ignores.
        """
        try:
            # Initialize negotiation state
            self._cap_state = {
                "host": host,
                "ls": set(),
                "ack": set(),
                "nak": set(),
                "pending": set(),
                "sasl_requested": False,
                "sasl_in_progress": False,
                "sasl_done": False,
                "end_sent": False,
                "using_tls": False,
            }
            # Try to infer TLS in use from last connect params if available
            try:
                self._cap_state["using_tls"] = (
                    True if getattr(self, "_last_connect_tls", False) else False
                )
            except Exception:
                pass
            # Save last creds for SASL
            self._cap_state["nick"] = nick or ""
            self._cap_state["sasl_user"] = sasl_user or nick or ""
            self._cap_state["password"] = password or ""

            # Desired capabilities (request intersection after LS)
            want = {
                "server-time",
                "message-tags",
                "echo-message",
                "chghost",
                "away-notify",
                "account-notify",
                "multi-prefix",
                "userhost-in-names",
                "labeled-response",
            }
            if password or sasl_user:
                want.add("sasl")
            # STARTTLS preference: note it, but actual upgrade likely requires bridge support
            if bool(getattr(self, "_try_starttls", False)) and not self._cap_state["using_tls"]:
                # Only mark interest; do not request here unless we can upgrade
                want.add("starttls")
            self._cap_state["want"] = set(want)

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
        st = getattr(self, "_cap_state", None)
        if st is None:
            return
        try:
            # CAP LS
            if " CAP " in line and " LS " in line:
                # Parse caps after ':'
                caps_part = line.split(":", 1)[1] if ":" in line else ""
                avail = set([c.split("=")[0] for c in caps_part.strip().split() if c])
                st["ls"] |= avail
                # Compute intersection and send CAP REQ for what's wanted
                req = (st.get("want") or set()) & st["ls"]
                if req:
                    st["pending"] |= req
                    self._send_raw("CAP REQ :" + " ".join(sorted(req)))
                else:
                    # No caps to request; we can end if not doing SASL
                    if not st.get("sasl_requested"):
                        self._send_raw("CAP END")
                        st["end_sent"] = True
                return

            # CAP ACK
            if " CAP " in line and " ACK " in line:
                caps_part = line.split(":", 1)[1] if ":" in line else ""
                acks = set([c.split("=")[0] for c in caps_part.strip().split() if c])
                st["ack"] |= acks
                st["pending"] -= acks
                # SASL start once ACK'd
                if (
                    "sasl" in acks
                    and not st["sasl_in_progress"]
                    and (st.get("password") or st.get("sasl_user"))
                ):
                    st["sasl_requested"] = True
                    st["sasl_in_progress"] = True
                    self._send_raw("AUTHENTICATE PLAIN")
                # STARTTLS path (note: likely unsupported without bridge socket upgrade)
                if (
                    "starttls" in acks
                    and not st["using_tls"]
                    and bool(getattr(self, "_try_starttls", False))
                ):
                    self.status.showMessage(
                        "Server supports STARTTLS; upgrade not attempted (bridge support required)",
                        4000,
                    )
                # If no pending and no SASL to perform, end
                if not st["pending"] and not st["sasl_in_progress"] and not st["end_sent"]:
                    self._send_raw("CAP END")
                    st["end_sent"] = True
                    self._persist_caps_ack()
                return

            # CAP NAK
            if " CAP " in line and " NAK " in line:
                caps_part = line.split(":", 1)[1] if ":" in line else ""
                naks = set([c.split("=")[0] for c in caps_part.strip().split() if c])
                st["nak"] |= naks
                st["pending"] -= naks
                # If no more pending and no SASL active, end
                if not st["pending"] and not st["sasl_in_progress"] and not st["end_sent"]:
                    self._send_raw("CAP END")
                    st["end_sent"] = True
                return

            # AUTHENTICATE + (server ready for payload)
            if line.endswith(" AUTHENTICATE +") and st.get("sasl_in_progress"):
                import base64

                u = st.get("sasl_user") or st.get("nick") or ""
                p = st.get("password") or ""
                mech = base64.b64encode((u + "\0" + u + "\0" + p).encode("utf-8")).decode("ascii")
                self._send_raw("AUTHENTICATE " + mech)
                return

            # SASL numerics handling
            # Success: 900 (logged in), 903 (SASL success)
            if any(code in line.split()[:2] for code in ("900", "903")) and st.get(
                "sasl_in_progress"
            ):
                st["sasl_in_progress"] = False
                st["sasl_done"] = True
                if not st["end_sent"]:
                    self._send_raw("CAP END")
                    st["end_sent"] = True
                    self._persist_caps_ack()
                self.status.showMessage("SASL authentication successful", 3000)
                return

            # Failures: 902 not logged in; 904-908 errors depending on server
            if any(
                code in line.split()[:2] for code in ("902", "904", "905", "906", "907", "908")
            ) and st.get("sasl_in_progress"):
                st["sasl_in_progress"] = False
                st["sasl_done"] = False
                if not st["end_sent"]:
                    self._send_raw("CAP END")
                    st["end_sent"] = True
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
            st = getattr(self, "_cap_state", None)
            if not st:
                return
            ack = sorted(st.get("ack") or [])
            host = st.get("host") or ""
            s = QSettings("DeadHop", "DeadHopClient")
            # Legacy
            s.setValue("server/capabilities_enabled", ack)
            # Host-scoped
            s.setValue(f"network/server_caps/{host}", ack)
        except Exception:
            pass

    # ----- Multi-server storage (QSettings: group 'servers') -----
    def _servers_list(self) -> list[str]:
        try:
            s = QSettings("DeadHop", "DeadHopClient")
            names = s.value("servers/names", [], type=list) or []
            return list(names)
        except Exception:
            return []

    def _servers_save(
        self,
        name: str,
        host: str,
        port: int,
        tls: bool,
        nick: str,
        user: str,
        realname: str,
        channels: list[str],
        autoconnect: bool,
        password: str | None,
        sasl_user: str | None,
        ignore_invalid_certs: bool = False,
    ) -> None:
        try:
            s = QSettings("DeadHop", "DeadHopClient")
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
            s = QSettings("DeadHop", "DeadHopClient")
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
            return (
                host,
                int(port),
                bool(tls),
                nick,
                user or "deadhop",
                realname or "DeadHop",
                list(channels),
                password,
                sasl_user,
                bool(autoconnect),
                bool(ignore_invalid_certs),
            )
        except Exception:
            return None

    def _servers_delete_name(self, name: str) -> None:
        try:
            s = QSettings("DeadHop", "DeadHopClient")
            names = [n for n in self._servers_list() if n != name]
            s.setValue("servers/names", names)
            base = f"servers/{name}"
            for key in (
                "host",
                "port",
                "tls",
                "nick",
                "user",
                "realname",
                "channels",
                "password",
                "sasl_user",
                "autoconnect",
                "ignore_invalid_certs",
            ):
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
                    (
                        host,
                        port,
                        tls,
                        nick,
                        user,
                        realname,
                        channels,
                        password,
                        sasl_user,
                        _auto,
                        ignore,
                    ) = data
                    # Include name so we can update its channels later
                    return (
                        n,
                        host,
                        port,
                        tls,
                        nick,
                        user,
                        realname,
                        channels,
                        password,
                        sasl_user,
                        ignore,
                    )
        except Exception:
            pass
        return None

    def _servers_set_autoconnect_name(self, name: str | None) -> None:
        try:
            s = QSettings("DeadHop", "DeadHopClient")
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
        if not nick:
            nick = self._default_nick()
        host = self._normalize_host(host)
        host, port, tls = self._resolve_connect_policy(host, port, tls)
        if tls:
            # Apply per-server TLS ignore-invalid-certs preference if applicable
            try:
                self._apply_tls_ignore_setting(ignore)
            except Exception:
                pass
        try:
            self._schedule_async(
                self.bridge.connectHost,
                host,
                port,
                tls,
                nick,
                user,
                realname,
                chans,
                password,
                sasl_user,
            )
            if getattr(self, "_auto_negotiate", True):
                self._schedule_async(
                    self._negotiate_on_connect, host, nick, user, password, sasl_user
                )
            self.status.showMessage(f"Connecting to {host}:{port}…", 2000)
            self._my_nick = nick
        except Exception:
            pass

    def _servers_add(self) -> None:
        dlg = ConnectDialog(self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            vals = dlg.values()
            (
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
            ) = vals
            name, ok = QInputDialog.getText(self, "Add Server", "Name:", text=f"{host}:{port}")
            if ok and name.strip():
                self._servers_save(
                    name.strip(),
                    host,
                    port,
                    tls,
                    nick,
                    user,
                    realname,
                    chans,
                    bool(autoconnect),
                    password,
                    sasl_user,
                    False,
                )

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
        host, port, tls, nick, user, realname, chans, password, sasl_user, autoconnect, ignore = (
            data
        )
        dlg = ConnectDialog(self)
        # Pre-fill via dialog setters if available; otherwise rely on internal defaults
        try:
            dlg.set_values(
                host, port, tls, nick, user, realname, chans, password, sasl_user, True, autoconnect
            )
        except Exception:
            pass
        if dlg.exec() == dlg.DialogCode.Accepted:
            vals = dlg.values()
            (
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
            ) = vals
            self._servers_save(
                name,
                host,
                port,
                tls,
                nick,
                user,
                realname,
                chans,
                bool(autoconnect),
                password,
                sasl_user,
                bool(ignore),
            )

    def _servers_set_ignore_invalid_certs(self) -> None:
        names = self._servers_list()
        if not names:
            self.toast_host.show_toast("No saved servers")
            return
        name, ok = QInputDialog.getItem(self, "Ignore Invalid Certs", "Choose:", names, 0, False)
        if not ok or not name:
            return
        # Ask desired state
        state, ok2 = QInputDialog.getItem(
            self, "Ignore Invalid Certs", "Set to:", ["Yes", "No"], 0, False
        )
        if not ok2:
            return
        val = state == "Yes"
        data = self._servers_load(name)
        if not data:
            return
        host, port, tls, nick, user, realname, chans, password, sasl_user, autoconnect, _ignore = (
            data
        )
        self._servers_save(
            name,
            host,
            port,
            tls,
            nick,
            user,
            realname,
            chans,
            bool(autoconnect),
            password,
            sasl_user,
            val,
        )

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
        name, ok = QInputDialog.getItem(
            self,
            "Set Auto-connect",
            "Choose:",
            names,
            names.index(current) if current in names else 0,
            False,
        )
        if ok and name:
            self._servers_set_autoconnect_name(name)

    def _on_channels_updated(self, channels: list[str]) -> None:
        """Populate the sidebar with channels received from the bridge and select the first."""
        try:
            # Preserve existing PM entries, then merge with incoming channels
            preserve = [
                lbl for lbl in getattr(self, "_channel_labels", []) if str(lbl).startswith("[PM:")
            ]
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
                s = QSettings("DeadHop", "DeadHopClient")
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
                        if lbl and (lbl.startswith("#") or lbl.startswith("&")):
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
                # Clear network selection context when a channel is selected
                try:
                    self._selected_network = None
                except Exception:
                    pass
                self._unread[ch] = 0
                hl = self._highlights.get(ch, 0)
                try:
                    self.sidebar.set_unread(ch, 0, hl)
                except Exception:
                    pass
                # Best-effort: select channel in sidebar if API exists
                try:
                    sel = getattr(self.sidebar, "select_channel", None)
                    if callable(sel):
                        sel(ch)
                except Exception:
                    pass
                # Clear chat view and replay scrollback for the selected label (channel or server)
                try:
                    self.chat.page().runJavaScript(
                        "(function(){var c=document.getElementById('chat'); if(c) c.innerHTML='';})();"
                    )
                except Exception:
                    pass
                try:
                    self._replay_scrollback(ch)
                except Exception:
                    pass
                # Refresh members list and completion names from cache, if available
                try:
                    names = self._names_by_channel.get(ch, [])
                    self.members.set_members(list(names))
                    self.composer.set_completion_names(list(names))
                except Exception:
                    pass
                self.status.showMessage(f"Switched to {ch}", 1500)
        except Exception:
            pass

    # ----- AI integration -----
    def _start_ai_chat(self) -> None:
        # Ask for model name (only requirement)
        model, ok = QInputDialog.getText(
            self, "AI Model", "Enter Ollama model name:", text="llama3"
        )
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
        try:
            self._chat_append(f"<i>AI session started with model: {model.strip()}</i>")
        except Exception:
            pass
        # Auto greet to verify connectivity
        try:
            self._chat_append("<i>DeadHop:</i> sending hello…")
            self._run_ai_inference(label, "hello")
        except Exception:
            pass

    def _run_ai_inference(self, ai_channel: str, prompt: str) -> None:
        # Extract model name from channel label [AI:model]
        model = (
            ai_channel[4:-1]
            if ai_channel.startswith("[AI:") and ai_channel.endswith("]")
            else ai_channel
        )
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
        try:
            self._chat_start_ai_line()
        except Exception:
            pass
        # reset buffer for routing
        self._ai_accum = ""
        self._ai_stream_open = True
        self._ai_thread.start()

    def _ai_chunk(self, text: str) -> None:
        # Append incremental text to the last line
        try:
            self._chat_ai_chunk(text)
        except Exception:
            pass
        # Accumulate for routing if enabled and stream out on thresholds
        if self._ai_route_target:
            self._ai_accum += text
            # Flush heuristics: newline, sentence end, or buffer too large
            if ("\n" in text) or text.endswith((". ", "! ", "? ")) or len(self._ai_accum) >= 320:
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
        item, ok = QInputDialog.getItem(
            self,
            "Route AI Output",
            "Choose target channel:",
            options,
            options.index(current) if current in options else 0,
            False,
        )
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
            cut = s.rfind(" ", 0, limit)
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
