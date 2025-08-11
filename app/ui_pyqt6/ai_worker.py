from __future__ import annotations
from typing import Optional
from PyQt6.QtCore import QObject, pyqtSignal
from ..ai.ollama import stream_generate


class OllamaStreamWorker(QObject):
    chunk = pyqtSignal(str)
    done = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, model: str, prompt: str, host: str = "127.0.0.1", port: int = 11434):
        super().__init__()
        self.model = model
        self.prompt = prompt
        self.host = host
        self.port = port
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run(self) -> None:
        try:
            for obj in stream_generate(self.model, self.prompt, self.host, self.port):
                if self._stopped:
                    break
                if "response" in obj:
                    self.chunk.emit(obj["response"])  # incremental tokens
                if obj.get("done"):
                    break
            self.done.emit()
        except Exception as e:
            self.error.emit(str(e))
