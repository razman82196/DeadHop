from __future__ import annotations

import asyncio
from collections.abc import Iterable

from PyQt6.QtCore import QObject, pyqtSignal
from qasync import asyncSlot

from ..irc.manager import IRCManager, ServerProfile


class BridgeQt(QObject):
    statusChanged = pyqtSignal(str)
    messageReceived = pyqtSignal(str, str, str, float)  # nick, target, text, ts
    namesUpdated = pyqtSignal(str, list)  # channel, names
    currentChannelChanged = pyqtSignal(str)
    channelsUpdated = pyqtSignal(list)
    monitorOnline = pyqtSignal(list)  # list of nicks
    monitorOffline = pyqtSignal(list)  # list of nicks
    # Typed events from IRCManager (network-aware)
    userJoined = pyqtSignal(str, str)  # composite channel, nick
    userParted = pyqtSignal(str, str)  # composite channel, nick
    userQuit = pyqtSignal(str, str)  # net, nick
    userNickChanged = pyqtSignal(str, str, str)  # net, old, new
    channelTopic = pyqtSignal(str, str, str)  # composite channel, actor, topic
    channelMode = pyqtSignal(str, str, str)  # composite channel, actor, modes_with_args
    channelModeUsers = pyqtSignal(str, list)  # composite channel, [(add, mode, nick)]

    def __init__(self):
        super().__init__()
        # Multiple networks keyed by id (use host as id for now)
        self._ircs: dict[str, IRCManager] = {}
        # Union list of composite labels like 'net:#chan'
        self._all_channels: list[str] = []
        self._current_channel: str | None = None

    def current_channel(self) -> str | None:
        return self._current_channel

    def set_current_channel(self, ch: str) -> None:
        if ch and ch != self._current_channel:
            self._current_channel = ch
            self.currentChannelChanged.emit(ch)

    # ----- Capability helpers -----
    def _current_net(self) -> str | None:
        cur = self._current_channel or ""
        if cur and ":" in cur and not cur.startswith("["):
            return cur.split(":", 1)[0]
        return None

    def hasCap(self, name: str) -> bool:
        """Return True if current network has the given IRCv3 capability active."""
        if not name:
            return False
        net = self._current_net()
        if not net:
            return False
        irc = self._ircs.get(net)
        if not irc:
            return False
        try:
            return bool(irc.has_cap(name))
        except Exception:
            return False

    def hasEchoMessage(self) -> bool:
        """Convenience for hasCap('echo-message')."""
        return self.hasCap("echo-message")

    @asyncSlot(str)
    async def disconnectNetwork(self, net: str) -> None:
        """Disconnect from a given network name and update channel list.

        Net should match the key used in composite labels (typically the host).
        """
        if not net:
            return
        irc = self._ircs.get(net)
        if not irc:
            return
        try:
            await irc.close()
        except Exception as e:
            self.statusChanged.emit(f"[{net}] Disconnect failed: {e}")
        # Remove network and its channels
        try:
            del self._ircs[net]
        except Exception:
            pass
        # Filter out channels belonging to this net
        self._all_channels = [c for c in self._all_channels if not c.startswith(f"{net}:")]
        self.channelsUpdated.emit(list(self._all_channels))
        # Adjust current channel if it belonged to the removed net
        cur = self._current_channel or ""
        if cur.startswith(f"{net}:"):
            self.set_current_channel(self._all_channels[0] if self._all_channels else "")

    @asyncSlot(str, int, bool, str, str, str, list, str, str, bool)
    async def connectHost(
        self,
        host: str,
        port: int = 6697,
        tls: bool = True,
        nick: str = "DeadHopUser",
        user: str = "peach",
        realname: str = "DeadHop",
        channels: Iterable[str] | None = None,
        password: str | None = None,
        sasl_user: str | None = None,
        ignore_invalid_certs: bool = False,
    ) -> None:
        # Avoid creating multiple connections to the same host (net id)
        try:
            if host in self._ircs and self._ircs.get(host):
                self.statusChanged.emit(f"[{host}] Already connected; skipping duplicate connect")
                return
        except Exception:
            pass
        self.statusChanged.emit(f"Connecting to {host}:{port} (TLS={'on' if tls else 'off'})…")
        # Normalize channels (ensure leading '#')
        norm_channels = []
        try:
            for ch in list(channels or []):
                ch = ch.strip()
                if not ch:
                    continue
                # If a composite like 'net:#chan' (or worse: '#net:#chan:...'), take the last segment
                if ":" in ch and not ch.startswith("["):
                    ch = ch.split(":")[-1]
                if not (ch.startswith("#") or ch.startswith("&")):
                    ch = "#" + ch
                norm_channels.append(ch)
        except Exception:
            norm_channels = list(channels or [])
        prof = ServerProfile(
            name=host,
            host=host,
            port=port,
            tls=tls,
            nick=nick,
            user=user,
            realname=realname,
            channels=list(dict.fromkeys(norm_channels)),
            password=password,
            sasl_user=sasl_user,
            ignore_invalid_certs=bool(ignore_invalid_certs),
        )
        net = host  # simple id; could include port if needed
        irc = IRCManager(prof)
        # Wire debug off by default (can be toggled via future UI option)
        try:
            irc.debug = True
        except Exception:
            pass
        # Prefix callbacks with network id, and emit composite labels
        irc.on_status = lambda s, _net=net: self.statusChanged.emit(f"[{_net}] {s}")
        irc.on_message = lambda n, t, x, ts, _net=net: self.messageReceived.emit(
            n, f"{_net}:{t}", x, ts
        )
        irc.on_names = lambda ch, ns, _net=net: self.namesUpdated.emit(f"{_net}:{ch}", ns)
        irc.on_join = lambda ch, nick, _net=net: self.userJoined.emit(f"{_net}:{ch}", nick)
        irc.on_part = lambda ch, nick, _net=net: self.userParted.emit(f"{_net}:{ch}", nick)
        irc.on_quit = lambda nick, _net=net: self.userQuit.emit(_net, nick)
        irc.on_nick = lambda old, new, _net=net: self.userNickChanged.emit(_net, old, new)
        irc.on_topic = lambda ch, actor, topic, _net=net: self.channelTopic.emit(
            f"{_net}:{ch}", actor, topic
        )
        irc.on_mode_channel = lambda ch, actor, modes, _net=net: self.channelMode.emit(
            f"{_net}:{ch}", actor, modes
        )
        irc.on_mode_users = lambda ch, changes, _net=net: self.channelModeUsers.emit(
            f"{_net}:{ch}", changes
        )
        irc.on_monitor_online = lambda nicks: self.monitorOnline.emit(nicks)
        irc.on_monitor_offline = lambda nicks: self.monitorOffline.emit(nicks)
        try:
            # Apply a sane timeout to avoid hanging forever on unreachable hosts
            await asyncio.wait_for(irc.connect(), timeout=15.0)
        except Exception as e:
            self.statusChanged.emit(f"Connect failed: {type(e).__name__}: {e}")
            return
        # Store manager
        self._ircs[net] = irc
        self.statusChanged.emit(f"[{net}] Connected. Registering…")
        # Build composite channel labels for this net
        new_list = [f"{net}:{c}" for c in list(prof.channels or [])]
        # Merge into union list (preserve order; append new ones)
        for lbl in new_list:
            if lbl not in self._all_channels:
                self._all_channels.append(lbl)
        # Set initial selection to first channel of this net if none selected
        if new_list and (self._current_channel is None):
            self.set_current_channel(new_list[0])
        # Notify UI with union list
        self.channelsUpdated.emit(list(self._all_channels))

    @asyncSlot(str)
    async def sendMessage(self, text: str) -> None:
        if not text:
            return
        target = self._current_channel or ""
        net, ch = self._split(target)
        if not net or not ch:
            return
        irc = self._ircs.get(net)
        if not irc:
            return
        try:
            await irc.send_privmsg(ch, text)
        except Exception as e:
            # Avoid bubbling to qasync error handler; report nicely
            self.statusChanged.emit(f"[{net}] Send failed to {ch}: {type(e).__name__}: {e}")
            return
        # Do not locally echo; rely on server echo (CAP echo-message) to avoid duplicates

    @asyncSlot(str, str)
    async def sendMessageTo(self, composite: str, text: str) -> None:
        if not composite or not text:
            return
        if composite.startswith("["):
            return
        net, ch = self._split(composite)
        if not net or not ch:
            return
        irc = self._ircs.get(net)
        if not irc:
            return
        try:
            await irc.send_privmsg(ch, text)
        except Exception as e:
            self.statusChanged.emit(f"[{net}] Send failed to {ch}: {type(e).__name__}: {e}")
            return
        # Do not locally echo; rely on server echo (CAP echo-message) to avoid duplicates

    @asyncSlot(str)
    async def sendRaw(self, line: str) -> None:
        """Send a raw IRC line to the current network, or all if none selected."""
        if not line:
            return
        # Prefer current network inferred from current_channel
        net = None
        cur = self._current_channel or ""
        if cur and ":" in cur and not cur.startswith("["):
            net = cur.split(":", 1)[0]
        targets = []
        if net and net in self._ircs:
            targets = [self._ircs[net]]
        else:
            targets = list(self._ircs.values())
        for irc in targets:
            try:
                await irc._send(line)
            except Exception:
                pass

    @asyncSlot(str)
    async def sendCommand(self, line: str) -> None:
        # Alias for sendRaw
        await self.sendRaw(line)

    @asyncSlot(list)
    async def setMonitorList(self, nicks: list[str]) -> None:
        # Apply to all active networks for now
        for net, irc in list(self._ircs.items()):
            try:
                await irc.monitor_set(nicks)
                self.statusChanged.emit(f"[{net}] Updated friends list ({len(nicks)})")
            except Exception as e:
                self.statusChanged.emit(f"[{net}] Monitor update failed: {e}")

    # ----- Channel management (multi-server aware) -----
    def _split(self, composite: str) -> tuple[str | None, str | None]:
        if not composite or composite.startswith("[") or ":" not in composite:
            return None, None
        parts = composite.split(":")
        # First segment is network id, last segment is the channel
        net = parts[0]
        ch = parts[-1]
        return net, ch

    @asyncSlot(str)
    async def joinChannel(self, composite: str) -> None:
        net, ch = self._split(composite)
        if not net or not ch:
            return
        irc = self._ircs.get(net)
        if not irc:
            return
        try:
            await irc.join(ch)
            # Request topic and names promptly to populate UI faster
            try:
                await irc._send(f"TOPIC {ch}")
            except Exception:
                pass
            try:
                await irc._send(f"NAMES {ch}")
            except Exception:
                pass
        except Exception as e:
            self.statusChanged.emit(f"[{net}] JOIN {ch} failed: {e}")
            return
        lbl = f"{net}:{ch}"
        if lbl not in self._all_channels:
            self._all_channels.append(lbl)
            self.channelsUpdated.emit(list(self._all_channels))
        # Switch current channel to the joined one
        self.set_current_channel(lbl)

    @asyncSlot(str)
    async def partChannel(self, composite: str) -> None:
        net, ch = self._split(composite)
        if not net or not ch:
            return
        irc = self._ircs.get(net)
        if not irc:
            return
        try:
            await irc.part(ch)
        except Exception as e:
            self.statusChanged.emit(f"[{net}] PART {ch} failed: {e}")
            return
        lbl = f"{net}:{ch}"
        # Optimistically remove from union list
        if lbl in self._all_channels:
            self._all_channels.remove(lbl)
            self.channelsUpdated.emit(list(self._all_channels))
        # If current was parted, select another
        if self._current_channel == lbl:
            self.set_current_channel(self._all_channels[0] if self._all_channels else "")

    @asyncSlot(str, str)
    async def setTopic(self, composite: str, topic: str) -> None:
        net, ch = self._split(composite)
        if not net or not ch:
            return
        irc = self._ircs.get(net)
        if not irc:
            return
        try:
            await irc.set_topic(ch, topic)
        except Exception as e:
            self.statusChanged.emit(f"[{net}] TOPIC set failed in {ch}: {e}")

    @asyncSlot(str, str)
    async def setModes(self, composite: str, modes: str) -> None:
        net, ch = self._split(composite)
        if not net or not ch:
            return
        irc = self._ircs.get(net)
        if not irc:
            return
        try:
            await irc.set_modes(ch, modes)
        except Exception as e:
            self.statusChanged.emit(f"[{net}] MODE change failed in {ch}: {e}")

    @asyncSlot(str)
    async def setMyModes(self, modes: str) -> None:
        """Set user modes for my own nick on the current network.

        Example: "+i", "-i", "+x", "-x", or combinations like "+ix".
        """
        if not modes:
            return
        # Determine current network from current channel selection
        net = None
        cur = self._current_channel or ""
        if cur and ":" in cur and not cur.startswith("["):
            net = cur.split(":", 1)[0]
        if not net or net not in self._ircs:
            return
        irc = self._ircs[net]
        nick = getattr(irc.p, "nick", None) or getattr(irc, "nick", None)
        if not nick:
            return
        try:
            await irc._send(f"MODE {nick} {modes}")
        except Exception as e:
            self.statusChanged.emit(f"[{net}] USER MODE change failed: {e}")
