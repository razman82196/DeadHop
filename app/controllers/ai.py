import json
from pathlib import Path

import requests

DATA_DIR = Path.home() / ".deadhop_local"
CONFIG_PATH = DATA_DIR / "config.json"


class DeadHopAI:
    def __init__(self):
        self.cfg = self._load()

    def _load(self):
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def call_local_llm(self, system_prompt: str, user_content: str) -> str:
        base = self.cfg.get("deadhop", {}).get("api_base", "http://127.0.0.1:11434")
        model = self.cfg.get("deadhop", {}).get("model", "llama3:8b")
        url = f"{base}/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "stream": False,
        }
        try:
            r = requests.post(url, json=payload, timeout=60)
            r.raise_for_status()
            data = r.json()
            parts = data.get("message", {}).get("content", "")
            if not parts and isinstance(data, dict):
                # Ollama compat: some versions return {"choices":[{"message":{"content":"..."}}]}
                ch = (data.get("choices") or [{}])[0]
                parts = ((ch or {}).get("message") or {}).get("content", "")
            return parts or ""
        except Exception as e:
            return f"[DeadHopAI] Error calling local LLM: {e}"


# Backwards-compat alias
PeachAI = DeadHopAI
