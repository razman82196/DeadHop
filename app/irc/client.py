import asyncio
from dataclasses import dataclass


@dataclass
class ServerConfig:
    name: str
    host: str
    port: int = 6697
    tls: bool = True
    nick: str = "PeachBot"
    realname: str = "Peach Client"
    channels: tuple = ("#peach",)


class AsyncIrcClient:
    def __init__(self, cfg: ServerConfig):
        self.cfg = cfg
        self.reader = None
        self.writer = None

    async def connect(self):
        # Minimal placeholder: actual IRC handshake to be implemented next iteration
        await asyncio.sleep(0.1)
        return True

    async def send_message(self, target: str, text: str):
        # Placeholder
        await asyncio.sleep(0)
