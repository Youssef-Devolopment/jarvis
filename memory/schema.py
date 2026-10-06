"""Versioned memory DB — PRAGMA user_version + forward-only migrations.

Every memory module (store/prefs/context/outcomes) opens the same
jarvis_memory.db file, so the schema version lives on the file itself.
store.ensure() adopts/updates it on first write; health reports it.

When the schema changes: bump SCHEMA_VERSION and add an entry to
_MIGRATIONS mapping the new version to a callable(conn). ensure() runs
missing steps in order from the stored version. Versions higher than
SCHEMA_VERSION (a newer JARVIS wrote this file) are left untouched and
reported so the user can downgrade/restore instead of corrupting data.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Callable, Dict

from logger import get_logger

log = get_logger("schema")

SCHEMA_VERSION = 1
_DB = Path(__file__).resolve().parent / "jarvis_memory.db"

# version -> migration step. v1 is the baseline (tables are created by
# CREATE TABLE IF NOT EXISTS in store.py), so no entry is needed for it.
_MIGRATIONS: Dict[int, Callable[[sqlite3.Connection], None]] = {}


def ensure(conn: sqlite3.Connection) -> dict:
    """Adopt or migrate a live connection's DB to SCHEMA_VERSION.

    Returns {ok, version, migrated, detail}. Never raises.
    """
    try:
        ver = int(conn.execute("PRAGMA user_version").fetchone()[0])
    except Exception as exc:
        return {"ok": False, "version": -1, "migrated": False,
                "detail": f"cannot read user_version: {exc}"[:160]}
    if ver == SCHEMA_VERSION:
        return {"ok": True, "version": ver, "migrated": False,
                "detail": f"v{ver} (current)"}
    if ver > SCHEMA_VERSION:
        detail = (f"v{ver} is newer than this build expects (v"
                  f"{SCHEMA_VERSION}) — left untouched")
        log.warning("Memory DB %s", detail)
        return {"ok": False, "version": ver, "migrated": False,
                "detail": detail}
    try:
        for target in range(ver + 1, SCHEMA_VERSION + 1):
            step = _MIGRATIONS.get(target)
            if step is not None:
                step(conn)
                log.info("Memory migration to v%s applied", target)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        try:
            conn.commit()
        except Exception:
            pass  # some callers manage their own commits
        log.info("Memory schema v%s -> v%s", ver, SCHEMA_VERSION)
        return {"ok": True, "version": ver, "migrated": True,
                "detail": f"v{ver} -> v{SCHEMA_VERSION}"}
    except Exception as exc:
        log.warning("Memory migration failed: %s", exc)
        return {"ok": False, "version": ver, "migrated": False,
                "detail": f"migration failed: {exc}"[:160]}


def status(path: Path | None = None) -> dict:
    """Read-only version report for /api/health (no connection kept open)."""
    p = Path(path) if path else _DB
    if not p.exists():
        return {"ok": True, "version": SCHEMA_VERSION, "exists": False,
                "detail": "new database (not created yet)"}
    conn = None
    try:
        conn = sqlite3.connect(str(p), timeout=3)
        ver = int(conn.execute("PRAGMA user_version").fetchone()[0])
    except Exception as exc:
        return {"ok": False, "version": -1, "exists": True,
                "detail": f"unreadable: {exc}"[:140]}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
    if ver == 0:
        return {"ok": True, "version": 0, "exists": True, "pending": True,
                "detail": "unversioned (adopts v1 on next write)"}
    if ver < SCHEMA_VERSION:
        return {"ok": True, "version": ver, "exists": True, "pending": True,
                "detail": f"v{ver} (migration to v{SCHEMA_VERSION} pending)"}
    if ver > SCHEMA_VERSION:
        return {"ok": False, "version": ver, "exists": True,
                "detail": f"v{ver} is newer than this build (v{SCHEMA_VERSION})"}
    return {"ok": True, "version": ver, "exists": True,
            "detail": f"v{ver} (current)"}
