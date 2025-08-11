import asyncio
import ssl
import time
import base64
from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class ServerProfile:
    name: str
    host: str
    port: int = 6697
    tls: bool = True
    nick: str = "PeachUser"
    user: str = "peach"
    realname: str = "Peach Client"
    channels: list[str] = None
    password: Optional[str] = None  # NickServ or SASL password
    sasl_user: Optional[str] = None  # SASL username (defaults to nick/user)
    # When True, disable certificate verification and hostname checks (self-signed certs)
    ignore_invalid_certs: bool = False


class IRCManager:
    def __init__(self, profile: ServerProfile):
        self.p = profile
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.on_message: Optional[Callable[[str, str, str, float], None]] = (
            None  # (nick, target, text, ts)
        )
        self.on_message_tags: Optional[Callable[[str, str, str, float, dict], None]] = (
            None  # (nick, target, text, ts, tags)
        )
        self.on_status: Optional[Callable[[str], None]] = None
        # User list/update callbacks
        self.on_names: Optional[Callable[[str, list[str]], None]] = None  # (channel, nicks)
        self.on_join: Optional[Callable[[str, str], None]] = None  # (channel, nick)
        self.on_part: Optional[Callable[[str, str], None]] = None  # (channel, nick)
        self.on_quit: Optional[Callable[[str], None]] = None  # (nick)
        self.on_nick: Optional[Callable[[str, str], None]] = None  # (old, new)
        self.on_who: Optional[Callable[[str, str], None]] = None  # (channel, nick)
        self.on_who_detail: Optional[Callable[[str, str, str, str, str, bool], None]] = (
            None  # (channel, nick, user, host, realname, away)
        )
        self.on_mode_users: Optional[Callable[[str, list[tuple[bool, str, str]]], None]] = (
            None  # (channel, [(add, mode_char, nick)])
        )
        self.on_away: Optional[Callable[[str, Optional[str]], None]] = (
            None  # (nick, away_msg or None)
        )
        self.on_account: Optional[Callable[[str, Optional[str]], None]] = (
            None  # (nick, account or None)
        )
        # IRCv3 extra callbacks
        self.on_chghost: Optional[Callable[[str, str, str], None]] = (
            None  # (nick, new_user, new_host)
        )
        self.on_setname: Optional[Callable[[str, str], None]] = None  # (nick, realname)
        self.on_labeled: Optional[Callable[[str, str, str, dict], None]] = (
            None  # (label, cmd, params, tags)
        )
        # WHOIS aggregated result callback: (nick, info_dict)
        self.on_whois: Optional[Callable[[str, dict], None]] = None
        # MONITOR callbacks: lists of nicks online/offline
        self.on_monitor_online: Optional[Callable[[list[str]], None]] = None
        self.on_monitor_offline: Optional[Callable[[list[str]], None]] = None
        self.current_channel = self.p.channels[0] if self.p.channels else None
        self._stop = False
        # IRCv3 state
        self._cap_negotiating = False
        self._available_caps: set[str] = set()
        self._requested_caps: set[str] = set()
        self._active_caps: set[str] = set()
        self._cap_ended = False
        self._registered = False
        self._welcome_received = False
        self._cap_ls_pending = False
        self._sasl_in_progress = False
        self._sasl_payload_sent = False
        # Batch state
        self._batches: dict[str, dict] = {}
        self._batch_names: dict[str, dict[str, list[str]]] = {}
        # WHOIS aggregation state
        self._whois_buf: dict[str, dict] = {}
        # Debug flag: when True, emit raw IRC lines via on_status
        self.debug: bool = False
        # MONITOR tracked nicks cache
        self._monitor: set[str] = set()

    async def connect(self):
        ctx = None
        server_hostname = None
        if self.p.tls:
            ctx = ssl.create_default_context()
            if getattr(self.p, "ignore_invalid_certs", False):
                try:
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                except Exception:
                    pass
            # Still provide SNI when possible
            server_hostname = self.p.host
        if ctx is not None:
            # Ensure SNI is sent for TLS servers
            self.reader, self.writer = await asyncio.open_connection(
                self.p.host, self.p.port, ssl=ctx, server_hostname=server_hostname
            )
        else:
            self.reader, self.writer = await asyncio.open_connection(self.p.host, self.p.port)
        # Start CAP negotiation (IRCv3)
        self._cap_negotiating = True
        if self.on_status:
            try:
                self.on_status("starting CAP negotiation (LS 302)")
            except Exception:
                pass
        await self._send("CAP LS 302")
        # Begin registration
        await self._send(f"NICK {self.p.nick}")
        await self._send(f"USER {self.p.user} 0 * :{self.p.realname}")
        if self.on_status:
            try:
                self.on_status("registering (NICK/USER sent)")
            except Exception:
                pass
        asyncio.create_task(self._reader_loop())

    async def _reader_loop(self):
        try:
            while not self._stop:
                line = await self.reader.readline()
                if not line:
                    # EOF from server
                    if self.on_status:
                        try:
                            self.on_status("server closed connection")
                        except Exception:
                            pass
                    break
                raw = line.decode(errors="ignore").rstrip("\r\n")
                if self.debug and self.on_status:
                    try:
                        self.on_status("<< " + raw)
                    except Exception:
                        pass

                # Extract IRCv3 message tags if present
                tags = {}
                rest_line = raw
                if raw.startswith("@"):
                    try:
                        tag_str, rest_line = raw[1:].split(" ", 1)
                        for part in tag_str.split(";"):
                            if "=" in part:
                                k, v = part.split("=", 1)
                            else:
                                k, v = part, ""
                            tags[k] = (
                                v.replace("\\:", ";")
                                .replace("\\s", " ")
                                .replace("\\r", "\r")
                                .replace("\\n", "\n")
                            )
                    except Exception:
                        rest_line = raw

                if rest_line.startswith("PING "):
                    await self._send("PONG " + raw.split(" ", 1)[1])
                    continue

                # Parse prefix/cmd/params once before handling numerics/commands
                prefix = ""
                cmd = ""
                params = ""
                if rest_line.startswith(":"):
                    try:
                        prefix, rest = rest_line[1:].split(" ", 1)
                    except ValueError:
                        prefix, rest = rest_line[1:], ""
                else:
                    rest = rest_line
                parts = rest.split(" ") if rest else []
                if parts:
                    cmd = parts[0]
                    params = " ".join(parts[1:])
                ucmd = cmd.upper() if cmd else ""

                # MONITOR responses
                if cmd == "730":
                    # RPL_MONONLINE: <me> :nick!user@host[,nick!user@host...]
                    try:
                        payload = rest.split(" :", 1)[1] if " :" in rest else ""
                        nicks = []
                        for item in payload.split(",") if payload else []:
                            n = item.split("!")[0].strip()
                            if n:
                                nicks.append(n)
                        if nicks and self.on_monitor_online:
                            self.on_monitor_online(nicks)
                    except Exception:
                        pass
                    continue
                if cmd == "731":
                    # RPL_MONOFFLINE: <me> :nick[,nick...]
                    try:
                        payload = rest.split(" :", 1)[1] if " :" in rest else ""
                        nicks = (
                            [p.split("!")[0].strip() for p in payload.split(",")] if payload else []
                        )
                        nicks = [n for n in nicks if n]
                        if nicks and self.on_monitor_offline:
                            self.on_monitor_offline(nicks)
                    except Exception:
                        pass
                    continue
                # Channel MODE changes affecting users: MODE #chan +ov nick1 nick2
                if ucmd == "MODE":
                    try:
                        parts2 = params.split()
                        ch = parts2[0] if parts2 else ""
                        if not ch.startswith(("#", "&")):
                            # user modes not handled here
                            pass
                        else:
                            mode_and_args = (rest_line.split(" :", 1)[0].split(" ", 2)[-1]).split()
                            if not mode_and_args:
                                raise Exception()
                            mode_seq = mode_and_args[0]
                            args = mode_and_args[1:]
                            add = None
                            ai = 0
                            changes = []
                            for chm in mode_seq:
                                if chm == "+":
                                    add = True
                                elif chm == "-":
                                    add = False
                                else:
                                    # only track user modes that take nick args
                                    if chm in ("q", "a", "o", "h", "v") and ai < len(args):
                                        changes.append((bool(add), chm, args[ai]))
                                        ai += 1
                            if changes and self.on_mode_users:
                                self.on_mode_users(ch, changes)
                    except Exception:
                        pass
                    continue

                # away-notify: AWAY [:message] from a user's prefix
                if ucmd == "AWAY":
                    try:
                        nick = prefix.split("!")[0]
                        msg = None
                        if " :" in rest_line:
                            msg = rest_line.split(" :", 1)[1]
                        if self.on_away:
                            self.on_away(nick, msg)
                    except Exception:
                        pass
                    continue

                # account-notify: ACCOUNT <name|*>
                if ucmd == "ACCOUNT":
                    try:
                        nick = prefix.split("!")[0]
                        acct = params.strip()
                        if acct == "*" or acct == "0":
                            acct = None
                        if self.on_account:
                            self.on_account(nick, acct)
                    except Exception:
                        pass
                    continue
                # WHO (352) and WHOX (354) minimal support: extract channel and nick
                if cmd == "352":
                    try:
                        parts2 = rest.split()
                        ch = parts2[1]
                        user = parts2[2]
                        host = parts2[3]
                        nick = parts2[5]
                        flags = parts2[6]
                        away = "G" in flags and "H" not in flags
                        # realname is after :
                        rn = rest.split(" :", 1)[1] if " :" in rest else ""
                        # rn may include hopcount at start; drop leading digits
                        realname = (
                            rn.split(" ", 1)[1]
                            if rn and rn.split(" ", 1)[0].isdigit() and " " in rn
                            else rn
                        )
                        if self.on_who_detail:
                            self.on_who_detail(ch, nick, user, host, realname, away)
                        elif self.on_who:
                            self.on_who(ch, nick)
                    except Exception:
                        pass
                    continue
                if cmd == "354":
                    try:
                        # WHOX custom fields vary; heuristically find channel and nick
                        parts2 = rest.split()
                        # common: <me> <type> <chan> <user> <ip/host> <nick> ...
                        ch = (
                            parts2[2]
                            if len(parts2) > 3 and parts2[2].startswith(("#", "&"))
                            else parts2[1]
                        )
                        # nick usually near the end; pick the last non-prefixed token
                        nick = parts2[-1]
                        if nick.startswith(":") and len(parts2) > 3:
                            nick = parts2[-2]
                        if self.on_who:
                            self.on_who(ch, nick.lstrip(":"))
                    except Exception:
                        pass
                    continue
                # (parsing moved earlier)

                # Labeled-response callback passthrough
                try:
                    lbl = tags.get("label") if tags else None
                    if lbl and self.on_labeled:
                        self.on_labeled(lbl, cmd, params, tags)
                except Exception:
                    pass

                # CAP negotiation flow
                if cmd == "CAP":
                    # Examples: ":server CAP nick LS :cap cap", ":server CAP nick ACK :cap cap"
                    try:
                        subcmd = parts[2] if len(parts) > 2 else ""
                        payload = rest.split(" :", 1)[1] if " :" in rest else ""
                    except Exception:
                        subcmd, payload = "", ""
                    await self._handle_cap(subcmd.upper(), payload)
                    continue

                # Registration welcome, used to know when server completed
                if cmd == "001":
                    self._welcome_received = True
                    if self.on_status:
                        try:
                            self.on_status("001 welcome received")
                        except Exception:
                            pass
                    # If no CAP or already ended, join now
                    if not self._cap_negotiating or self._cap_ended:
                        await self._join_initial()
                    continue

                # WHOIS numerics aggregation
                if cmd == "311":
                    # RPL_WHOISUSER: <me> <nick> <user> <host> * :<realname>
                    try:
                        parts2 = rest.split()
                        nick = parts2[1]
                        user = parts2[2]
                        host = parts2[3]
                        realname = rest.split(" :", 1)[1] if " :" in rest else ""
                        st = self._whois_buf.setdefault(nick, {})
                        st.update({"user": user, "host": host, "realname": realname})
                    except Exception:
                        pass
                    continue
                if cmd == "312":
                    # RPL_WHOISSERVER: <me> <nick> <server> :<server info>
                    try:
                        parts2 = rest.split()
                        nick = parts2[1]
                        server = parts2[2]
                        info = rest.split(" :", 1)[1] if " :" in rest else ""
                        st = self._whois_buf.setdefault(nick, {})
                        st.update({"server": server, "server_info": info})
                    except Exception:
                        pass
                    continue
                if cmd == "317":
                    # RPL_WHOISIDLE: <me> <nick> <idle> <signon> :seconds idle, signon time
                    try:
                        parts2 = rest.split()
                        nick = parts2[1]
                        idle = int(parts2[2]) if len(parts2) > 2 and parts2[2].isdigit() else None
                        signon = int(parts2[3]) if len(parts2) > 3 and parts2[3].isdigit() else None
                        st = self._whois_buf.setdefault(nick, {})
                        st.update({"idle": idle, "signon": signon})
                    except Exception:
                        pass
                    continue
                if cmd == "319":
                    # RPL_WHOISCHANNELS: <me> <nick> :@#chan +#chan ...
                    try:
                        parts2 = rest.split()
                        nick = parts2[1]
                        chans = rest.split(" :", 1)[1].split() if " :" in rest else []
                        st = self._whois_buf.setdefault(nick, {})
                        st.update({"channels": chans})
                    except Exception:
                        pass
                    continue
                if cmd == "330":
                    # RPL_WHOISACCOUNT: <me> <nick> <account> :is logged in as
                    try:
                        parts2 = rest.split()
                        nick = parts2[1]
                        account = parts2[2] if len(parts2) > 2 else None
                        st = self._whois_buf.setdefault(nick, {})
                        st.update({"account": account})
                    except Exception:
                        pass
                    continue
                if cmd == "338":
                    # RPL_WHOISACTUALLY (varies by daemon): <me> <nick> :is actually <host>
                    try:
                        parts2 = rest.split()
                        nick = parts2[1]
                        extra = rest.split(" :", 1)[1] if " :" in rest else ""
                        st = self._whois_buf.setdefault(nick, {})
                        st.update({"actually": extra})
                    except Exception:
                        pass
                    continue
                if cmd == "318":
                    # RPL_ENDOFWHOIS: <me> <nick> :End of WHOIS list
                    try:
                        parts2 = rest.split()
                        nick = parts2[1]
                        st = self._whois_buf.pop(nick, {})
                        if self.on_whois:
                            self.on_whois(nick, st)
                    except Exception:
                        pass
                    continue

                # SASL AUTHENTICATE exchange
                if cmd == "AUTHENTICATE":
                    # Server prompts with '+' to request payload
                    if (
                        params.strip() == "+"
                        and self._sasl_in_progress
                        and not self._sasl_payload_sent
                    ):
                        if self.on_status:
                            try:
                                self.on_status("SASL server requested payload (+)")
                            except Exception:
                                pass
                        await self._send(self._sasl_payload())
                        self._sasl_payload_sent = True
                    continue

                # SASL result numerics
                if cmd in ("903", "904", "905", "906", "907"):
                    # 903 = success; others are failure/abort/already authed
                    self._sasl_in_progress = False
                    if self.on_status:
                        try:
                            self.on_status(f"SASL result {cmd}")
                        except Exception:
                            pass
                    await self._end_cap()
                    continue

                # PRIVMSG :
                if cmd.upper() == "PRIVMSG" and " :" in rest_line:
                    try:
                        target = params.split(" ", 1)[0]
                        text = rest_line.split(" :", 1)[1]
                        # Prefer server-time tag if present
                        ts = self._ts_from_tags(tags) or time.time()
                        nick = prefix.split("!")[0] if "!" in prefix else prefix
                        if self.on_message:
                            self.on_message(nick, target, text, ts)
                        if self.on_message_tags:
                            self.on_message_tags(nick, target, text, ts, tags or {})
                    except Exception:
                        pass
                    continue

                # JOIN/PART/QUIT/NICK/CHGHOST/SETNAME
                ucmd = cmd.upper()
                if ucmd == "JOIN":
                    try:
                        ch = rest_line.split(" :", 1)[1] if " :" in rest_line else params
                        nick = prefix.split("!")[0]
                        if self.on_join:
                            self.on_join(ch, nick)
                    except Exception:
                        pass
                    continue
                if ucmd == "PART":
                    try:
                        ch = params.split(" ", 1)[0]
                        nick = prefix.split("!")[0]
                        if self.on_part:
                            self.on_part(ch, nick)
                    except Exception:
                        pass
                    continue
                if ucmd == "QUIT":
                    try:
                        nick = prefix.split("!")[0]
                        if self.on_quit:
                            self.on_quit(nick)
                    except Exception:
                        pass
                    continue
                if ucmd == "NICK":
                    try:
                        newnick = rest.split(" :", 1)[1] if " :" in rest else params
                        old = prefix.split("!")[0]
                        if self.on_nick:
                            self.on_nick(old, newnick)
                    except Exception:
                        pass
                    continue
                if ucmd == "CHGHOST":
                    try:
                        # CHGHOST <newuser> <newhost>
                        parts2 = params.split()
                        newuser = parts2[0] if len(parts2) > 0 else ""
                        newhost = parts2[1] if len(parts2) > 1 else ""
                        nick = prefix.split("!")[0]
                        if self.on_chghost:
                            self.on_chghost(nick, newuser, newhost)
                    except Exception:
                        pass
                    continue
                if ucmd == "SETNAME":
                    try:
                        # SETNAME :new realname
                        rn = rest.split(" :", 1)[1] if " :" in rest else params
                        nick = prefix.split("!")[0]
                        if self.on_setname:
                            self.on_setname(nick, rn)
                    except Exception:
                        pass
                    continue

                # BATCH open/close
                if cmd.upper() == "BATCH":
                    try:
                        tok = params.split()
                        if not tok:
                            raise Exception()
                        ident = tok[0]
                        if ident.startswith("+"):
                            bid = ident[1:]
                            btype = tok[1] if len(tok) > 1 else ""
                            self._batches[bid] = {"type": btype}
                            # init names buffer if needed
                            self._batch_names.setdefault(bid, {})
                        elif ident.startswith("-"):
                            bid = ident[1:]
                            # flush any buffered names
                            if bid in self._batch_names and self.on_names:
                                for ch, lst in self._batch_names[bid].items():
                                    if lst:
                                        self.on_names(ch, lst)
                            self._batch_names.pop(bid, None)
                            self._batches.pop(bid, None)
                    except Exception:
                        pass
                    continue

                # NAMES reply 353 / end 366: :server 353 <me> = #chan :@op +v nick2 nick3
                if cmd == "353":
                    try:
                        # params: <me> <type> <chan> :names...
                        parts2 = rest.split(" :", 1)
                        left = parts2[0].split()
                        ch = left[-1]
                        names = parts2[1].split() if len(parts2) > 1 else []
                        bid = (tags or {}).get("batch")
                        if bid:
                            bychan = self._batch_names.setdefault(bid, {})
                            bychan.setdefault(ch, []).extend(names)
                        else:
                            # Pass raw names with prefixes; model will parse modes
                            if self.on_names:
                                self.on_names(ch, names)
                    except Exception:
                        pass
                    continue
        except Exception as e:
            if self.on_status:
                try:
                    self.on_status(f"reader error: {type(e).__name__}: {e}")
                except Exception:
                    pass
        finally:
            if self.on_status:
                try:
                    self.on_status("disconnected")
                except Exception:
                    pass

    async def _handle_cap(self, subcmd: str, payload: str):
        if subcmd == "LS":
            # Handle possible multi-line LS with '*'
            # payload contains caps; check for continuation via parts[2] == '*'
            caps = payload.split()
            self._available_caps.update(caps)
            # If this LS had continuation marker, keep waiting for final LS
            # We cannot rely on payload alone to know '*', so detect via presence of trailing '*' token earlier.
            # As we don't have it here, approximate: if we haven't requested yet and caps look partial, we wait for ACK/another LS.
            # To be safe, require a second LS to proceed unless we've seen LS before.
            if not self._cap_ls_pending and not self._requested_caps:
                # First LS seen; set pending and wait for another CAP LS or proceed after short delay
                self._cap_ls_pending = True
                # Optimistically proceed immediately (works on most daemons)
            # Decide what to request
            # Request a broad set of IRCv3 capabilities for presence and UX parity
            want = {
                "server-time",
                "message-tags",
                "echo-message",
                "account-notify",
                "away-notify",
                "chghost",
                "setname",
                "batch",
                "labeled-response",
                "multi-prefix",
            }
            if self.p.password:
                want.add("sasl")
            req = sorted(want.intersection(self._available_caps))
            if req and not self._requested_caps:
                self._requested_caps.update(req)
                await self._send("CAP REQ :" + " ".join(req))
            elif not req:
                await self._end_cap()
        elif subcmd == "ACK":
            acks = payload.split()
            self._active_caps.update(acks)
            if "sasl" in acks and self.p.password:
                await self._begin_sasl()
            else:
                await self._end_cap()
        elif subcmd == "NAK":
            await self._end_cap()

    async def _begin_sasl(self):
        try:
            self._sasl_in_progress = True
            self._sasl_payload_sent = False
            await self._send("AUTHENTICATE PLAIN")
        except Exception:
            await self._end_cap()

    def _sasl_payload(self) -> str:
        authzid = ""  # empty authzid
        authcid = self.p.sasl_user or self.p.user or self.p.nick
        passwd = self.p.password or ""
        msg = f"{authzid}\x00{authcid}\x00{passwd}".encode()
        b64 = base64.b64encode(msg).decode()
        return f"AUTHENTICATE {b64}"

    async def _end_cap(self):
        if not self._cap_ended:
            await self._send("CAP END")
            self._cap_ended = True
            # If welcome already received, we can join
            if self._welcome_received:
                await self._join_initial()

    # ----- Public convenience commands -----
    async def join(self, channel: str):
        ch = channel.strip()
        if not ch:
            return
        await self._send(f"JOIN {ch}")

    async def part(self, channel: str, reason: str | None = None):
        ch = channel.strip()
        if not ch:
            return
        if reason:
            await self._send(f"PART {ch} :{reason}")
        else:
            await self._send(f"PART {ch}")

    async def set_topic(self, channel: str, topic: str):
        ch = channel.strip()
        await self._send(f"TOPIC {ch} :{topic}")

    async def set_modes(self, channel: str, modes: str):
        ch = channel.strip()
        await self._send(f"MODE {ch} {modes}")

    async def _join_initial(self):
        # Join initial channels
        for ch in self.p.channels or []:
            await self._send(f"JOIN {ch}")

    def _ts_from_tags(self, tags: dict) -> Optional[float]:
        t = tags.get("time") if tags else None
        if not t:
            return None
        try:
            # RFC3339/ISO8601: 2023-10-11T12:34:56.789Z
            from datetime import datetime

            if t.endswith("Z"):
                t = t[:-1] + "+00:00"
            dt = datetime.fromisoformat(t)
            return dt.timestamp()
        except Exception:
            return None

    async def _send(self, line: str):
        if self.writer is None:
            return
        if self.debug and self.on_status:
            try:
                # Hide auth payloads
                log = line if not line.startswith("AUTHENTICATE ") else "AUTHENTICATE <hidden>"
                self.on_status(">> " + log)
            except Exception:
                pass
        self.writer.write((line + "\r\n").encode())
        await self.writer.drain()

    async def send_privmsg(self, target: str, text: str):
        await self._send(f"PRIVMSG {target} :{text}")

    def has_cap(self, name: str) -> bool:
        return name in self._active_caps

    # ----- IRCv3 MONITOR helpers -----
    async def monitor_set(self, nicks: list[str]):
        # Replace current monitor list with given nicks
        try:
            await self._send("MONITOR C")  # clear existing
        except Exception:
            pass
        self._monitor = set(n.strip() for n in nicks if n.strip())
        if self._monitor:
            joined = ",".join(sorted(self._monitor))
            await self._send(f"MONITOR + {joined}")

    async def monitor_add(self, nicks: list[str]):
        add = set(n.strip() for n in nicks if n.strip()) - self._monitor
        if not add:
            return
        self._monitor.update(add)
        joined = ",".join(sorted(add))
        await self._send(f"MONITOR + {joined}")

    async def monitor_remove(self, nicks: list[str]):
        rem = set(n.strip() for n in nicks if n.strip()) & self._monitor
        if not rem:
            return
        self._monitor.difference_update(rem)
        joined = ",".join(sorted(rem))
        await self._send(f"MONITOR - {joined}")

    async def close(self):
        self._stop = True
        try:
            await self._send("QUIT :bye")
        except Exception:
            pass
        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass
