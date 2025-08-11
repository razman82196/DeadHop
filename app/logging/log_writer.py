from __future__ import annotations
import os
import time
from pathlib import Path

class LogWriter:
    def __init__(self, base_dir: str | None = None) -> None:
        # Default logs dir within project if not provided
        self.base = Path(base_dir or Path.cwd() / "logs")
        self.base.mkdir(parents=True, exist_ok=True)

    def _path_for(self, network: str, channel: str) -> Path:
        safe_net = (network or "irc").strip().replace(os.sep, "_")
        safe_chan = (channel or "misc").strip().replace(os.sep, "_")
        p = self.base / safe_net
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{safe_chan}.log"

    def append(self, network: str, channel: str, line: str, ts: float | None = None) -> None:
        path = self._path_for(network, channel)
        t = ts or time.time()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))
        with path.open("a", encoding="utf-8", errors="ignore") as f:
            f.write(f"[{stamp}] {line}\n")

    # Public accessor for consumers that need to open the file
    def path_for(self, network: str, channel: str) -> Path:
        return self._path_for(network, channel)
