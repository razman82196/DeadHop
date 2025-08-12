from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

WELCOME = [
    ":tiny.server 001 {nick} :Welcome to TinyIRCD",
    ":tiny.server 005 {nick} CHANTYPES=# PREFIX=(ov)@+ NETWORK=TinyNet :are supported",
    ":tiny.server 375 {nick} :- TinyIRCD MOTD -",
    ":tiny.server 372 {nick} :- offline scripted server for tests",
    ":tiny.server 376 {nick} :End of /MOTD command.",
]


@dataclass
class ScriptEvent:
    delay_ms: int
    line: str


def load_script(path: Path) -> list[ScriptEvent]:
    events: list[ScriptEvent] = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        # format: <delay_ms> <rawline>
        try:
            d, rest = ln.split(" ", 1)
            events.append(ScriptEvent(int(d), rest))
        except Exception:
            continue
    return events


class TinyIRCD(asyncio.Protocol):
    def __init__(self, script: list[ScriptEvent]):
        self.script = script
        self.transport: asyncio.Transport | None = None
        self.nick = "guest"

    def connection_made(self, transport: asyncio.Transport) -> None:
        self.transport = transport

    def data_received(self, data: bytes) -> None:
        text = data.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            self.handle_line(line.strip())

    def handle_line(self, line: str) -> None:
        if not self.transport:
            return
        # Simple handlers for NICK/USER/JOIN
        if line.upper().startswith("NICK "):
            self.nick = line.split(" ", 1)[1].strip()
            return
        if line.upper().startswith("USER "):
            # Send welcome
            for line_tmpl in WELCOME:
                self.send(line_tmpl.format(nick=self.nick))
            return
        if line.upper().startswith("JOIN "):
            try:
                ch = line.split(" ", 1)[1].strip().split(",")[0]
            except Exception:
                ch = "#test"
            # Topic + names + end
            self.send(f":tiny.server 332 {self.nick} {ch} :Scripted channel")
            self.send(f":tiny.server 353 {self.nick} = {ch} :@alice +bob {self.nick}")
            self.send(f":tiny.server 366 {self.nick} {ch} :End of /NAMES list.")
            # Schedule scripted events
            loop = asyncio.get_event_loop()
            t = 0
            for ev in self.script:
                t += ev.delay_ms
                loop.call_later(t / 1000.0, self.send, ev.line)
            return
        # Echo PRIVMSG/others as NOTICE
        if line.upper().startswith("PRIVMSG "):
            try:
                target, body = line.split(" ", 1)[1].split(" :", 1)
                self.send(f":tiny.server NOTICE {target} :echo: {body}")
            except Exception:
                pass

    def send(self, line: str) -> None:
        if self.transport:
            self.transport.write((line + "\r\n").encode("utf-8"))


async def main_async(port: int, script_path: Path) -> int:
    script = load_script(script_path) if script_path.exists() else []
    loop = asyncio.get_running_loop()
    server = await loop.create_server(lambda: TinyIRCD(script), host="127.0.0.1", port=port)
    print(f"TinyIRCD listening on 127.0.0.1:{port}")
    async with server:
        await server.serve_forever()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=6667)
    parser.add_argument(
        "--script", type=Path, default=Path("app/tests/fixtures/tiny_scenario.script")
    )
    args = parser.parse_args()
    return asyncio.run(main_async(args.port, args.script))


if __name__ == "__main__":
    raise SystemExit(main())
