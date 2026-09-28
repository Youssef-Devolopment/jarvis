from __future__ import annotations
from threading import Lock
from logger import get_logger

log = get_logger(__name__)
_lock = Lock()
_disabled = set()

_ALL = ["web_search", "open_url", "read_current_page",
        "remember_fact", "switch_mood", "read_own_code"]


def all_tools():
    with _lock:
        return [{"name": n, "enabled": n not in _disabled} for n in _ALL]


def is_enabled(name: str) -> bool:
    with _lock:
        return name not in _disabled


def toggle_tool(name: str, enabled: bool) -> bool:
    if name not in _ALL:
        return False
    with _lock:
        if enabled:
            _disabled.discard(name)
        else:
            _disabled.add(name)
    return True


def filtered_schemas(schemas: list) -> list:
    return [s for s in schemas
            if is_enabled(s.get("function", {}).get("name", ""))]
