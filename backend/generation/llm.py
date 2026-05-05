from __future__ import annotations

import json
from typing import Generator, Iterator

import requests


_DEFAULT_MODEL = "llama3.2:8b"
_DEFAULT_URL = "http://localhost:11434"


def stream(
    prompt: str,
    model: str = _DEFAULT_MODEL,
    base_url: str = _DEFAULT_URL,
) -> Generator[str, None, None]:
    """Yield text tokens from Ollama /api/generate as they arrive.

    Calls Ollama with stream=True, parses NDJSON line by line, and yields
    each non-empty 'response' token until the server signals done=true.
    Raises requests.HTTPError on non-2xx status.
    """
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {"model": model, "prompt": prompt, "stream": True}

    with requests.post(url, json=payload, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        yield from _parse_stream(resp.iter_lines())


def _parse_stream(lines: Iterator) -> Generator[str, None, None]:
    """Parse NDJSON lines from an Ollama stream, yielding text tokens."""
    for line in lines:
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8")
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        token = data.get("response", "")
        if token:
            yield token
        if data.get("done", False):
            break
