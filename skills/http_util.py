"""Shared HTTP helper for all skills — avoids 14 duplicate copies."""

from __future__ import annotations
import json
import urllib.request
from typing import Any

UA = "JARVIS/1.0"


def http_get(url: str, timeout: float = 8.0, as_json: bool = False) -> Any:
    """GET a URL. Returns text, or parsed JSON if as_json=True."""
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", errors="replace")
        if as_json:
            return json.loads(raw)
        return raw


def http_get_bytes(url: str, timeout: float = 8.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()
