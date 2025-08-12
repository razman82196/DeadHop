from __future__ import annotations

import json
from collections.abc import Iterator

import requests

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 11434


def is_server_up(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    url = f"http://{host}:{port}/api/version"
    try:
        r = requests.get(url, timeout=2)
        return r.ok
    except Exception:
        return False


def stream_generate(
    model: str,
    prompt: str,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    options: dict | None = None,
) -> Iterator[dict]:
    """
    Yields JSON objects from Ollama /api/generate streaming endpoint.
    Each yielded item typically has keys like: {"model", "response", "done", ...}
    """
    url = f"http://{host}:{port}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": True,
    }
    if options:
        payload["options"] = options
    with requests.post(url, json=payload, stream=True, timeout=60) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            try:
                obj = json.loads(line)
            except Exception:
                continue
            yield obj
