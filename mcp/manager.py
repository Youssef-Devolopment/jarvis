from __future__ import annotations

import json
import uuid
from pathlib import Path
from threading import Lock

from logger import get_logger

log = get_logger(__name__)
_CONFIG = Path(__file__).resolve().parent.parent / "mcp_servers.json"
_lock = Lock()

# First run: a fresh install ships no mcp_servers.json (it is personal
# and gitignored) and nothing seeded it, so MCP came up empty for every
# new user — the panel said "None yet" and the system looked broken.
# Seed presets that need neither an API key nor an argument, so every
# one of them works the moment it starts.
FIRST_RUN_PRESETS = ("fetch", "memory", "sequential-thinking")
_seeded = False


def _load():
    if not _CONFIG.exists():
        return []
    try:
        return json.loads(_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items):
    _CONFIG.write_text(json.dumps(items, indent=2), encoding="utf-8")


def ensure_seeded() -> list:
    """Create the first-run MCP config. Returns what was seeded.

    An existing file — even an empty one — means the user decided, so
    we never re-seed. Runs outside the read that follows, taking the
    lock itself: `all_servers()` would otherwise re-enter it.
    """
    global _seeded
    if _seeded:
        return []
    with _lock:
        if _seeded:
            return []
        _seeded = True
        if _CONFIG.exists():
            return []
        from mcp.presets import get_preset
        items = []
        for pid in FIRST_RUN_PRESETS:
            p = get_preset(pid)
            if not p:
                continue
            items.append({"id": uuid.uuid4().hex[:8], "name": p["name"],
                          "command": p["command"], "args": p["args"].split(),
                          "enabled": True})
        if items:
            _save(items)
            log.info("first run: seeded %d MCP preset(s): %s",
                     len(items), ", ".join(i["name"] for i in items))
        return items


def all_servers():
    ensure_seeded()
    with _lock:
        return _load()


def add_server(name, command, args="", enabled=True):
    if not name or not command:
        return {"error": "Name and command required."}
    if isinstance(args, (list, tuple)):
        arg_list = [str(a).strip() for a in args if str(a).strip()]
    else:
        arg_list = [a.strip() for a in args.split()
                    if a.strip()] if args else []
    with _lock:
        items = [s for s in _load() if s.get("name") != name]
        entry = {"id": uuid.uuid4().hex[:8], "name": name.strip(),
                 "command": command.strip(),
                 "args": arg_list,
                 "enabled": bool(enabled)}
        items.append(entry)
        _save(items)
    return entry


def remove_server(sid):
    with _lock:
        items = _load()
        before = len(items)
        items = [s for s in items if s.get("id") != sid]
        if len(items) == before:
            return False
        _save(items)
    return True


def toggle_server(sid, enabled):
    with _lock:
        items = _load()
        found = False
        for s in items:
            if s.get("id") == sid:
                s["enabled"] = bool(enabled)
                found = True
                break
        if found:
            _save(items)
    return found
