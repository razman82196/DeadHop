from __future__ import annotations
import asyncio
from typing import Optional, Iterable, Dict, List

from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot as Slot
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

    def __init__(self):
        super().__init__()
        # Multiple networks keyed by id (use host as id for now)
        self._ircs: Dict[str, IRCManager] = {}
        # Union list of composite labels like 'net:#chan'
        self._all_channels: List[str] = []
        self._current_channel: Optional[str] = None

    def current_channel(self) -> Optional[str]:
        return self._current_channel

    def set_current_channel(self, ch: str) -> None:
        if ch and ch != self._current_channel:
            self._current_channel = ch
            self.currentChannelChanged.emit(ch)

    @asyncSlot(str, int, bool, str, str, str, list, str, str, bool)
    async def connectHost(
        self,
        host: str,
        port: int = 6697,
        tls: bool = True,
        nick: str = "PeachUser",
        user: str = "peach",
        realname: str = "Peach Client",
        channels: Iterable[str] | None = None,
        password: str | None = None,
        sasl_user: str | None = None,
        ignore_invalid_certs: bool = False,
    ) -> None:
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
                if not (ch.startswith('#') or ch.startswith('&')):
                    ch = '#' + ch
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
        irc.on_message = lambda n, t, x, ts, _net=net: self.messageReceived.emit(n, f"{_net}:{t}", x, ts)
        irc.on_names = lambda ch, ns, _net=net: self.namesUpdated.emit(f"{_net}:{ch}", ns)
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
        await irc.send_privmsg(ch, text)
        # Echo message locally to the composite target
        self.messageReceived.emit("You", f"{net}:{ch}", text, asyncio.get_event_loop().time())

    @asyncSlot(str, str)
    async def sendMessageTo(self, composite: str, text: str) -> None:
        if not composite or not text:
            return
        if composite.startswith('['):
            return
        net, ch = self._split(composite)
        if not net or not ch:
            return
        irc = self._ircs.get(net)
        if not irc:
            return
        await irc.send_privmsg(ch, text)
        self.messageReceived.emit("You", f"{net}:{ch}", text, asyncio.get_event_loop().time())

    @asyncSlot(str)
    async def sendRaw(self, line: str) -> None:
        """Send a raw IRC line to the current network, or all if none selected."""
        if not line:
            return
        # Prefer current network inferred from current_channel
        net = None
        cur = self._current_channel or ""
        if cur and ':' in cur and not cur.startswith('['):
            net = cur.split(':', 1)[0]
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
    def _split(self, composite: str) -> tuple[Optional[str], Optional[str]]:
        if not composite or composite.startswith('[') or ':' not in composite:
            return None, None
        parts = composite.split(':')
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
