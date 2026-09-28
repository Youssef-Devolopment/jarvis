"""Context tracker — record of what JARVIS is doing on the PC."""
from __future__ import annotations
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_DB = Path(__file__).resolve().parent / "jarvis_memory.db"
_lock = threading.Lock()


def _conn():
    c = sqlite3.connect(str(_DB), check_same_thread=False)
    c.execute("""CREATE TABLE IF NOT EXISTS context_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL,
        detail TEXT NOT NULL,
        timestamp TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_ctx_ts ON context_events(timestamp DESC)")
    c.execute("""CREATE TABLE IF NOT EXISTS session_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        summary TEXT)""")
    c.commit()
    return c


def log_event(kind: str, detail: str) -> None:
    try:
        with _lock:
            c = _conn()
            c.execute("INSERT INTO context_events (kind, detail, timestamp) VALUES (?,?,?)",
                      (kind, detail[:500], datetime.now().isoformat(timespec="seconds")))
            c.commit()
            c.close()
    except Exception as exc:
        log.debug("Context log failed: %s", exc)


def recent_events(minutes: int = 60, limit: int = 30) -> list:
    since = (datetime.now() - timedelta(minutes=minutes)).isoformat(timespec="seconds")
    try:
        with _lock:
            c = _conn()
            rows = c.execute(
                "SELECT kind, detail, timestamp FROM context_events "
                "WHERE timestamp > ? ORDER BY id DESC LIMIT ?",
                (since, limit)).fetchall()
            c.close()
        return [{"kind": r[0], "detail": r[1], "timestamp": r[2]} for r in rows]
    except Exception:
        return []


def recent_errors(hours: int = 24, limit: int = 10) -> list:
    since = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
    try:
        with _lock:
            c = _conn()
            rows = c.execute(
                "SELECT detail, timestamp FROM context_events "
                "WHERE kind = 'error' AND timestamp > ? ORDER BY id DESC LIMIT ?",
                (since, limit)).fetchall()
            c.close()
        return [{"detail": r[0], "timestamp": r[1]} for r in rows]
    except Exception:
        return []


def start_session() -> int:
    try:
        with _lock:
            c = _conn()
            cur = c.execute("INSERT INTO session_log (started_at) VALUES (?)",
                            (datetime.now().isoformat(timespec="seconds"),))
            c.commit()
            sid = cur.lastrowid
            c.close()
            return sid or 0
    except Exception:
        return 0


def end_session(sid: int, summary: str = "") -> None:
    try:
        with _lock:
            c = _conn()
            c.execute("UPDATE session_log SET ended_at = ?, summary = ? WHERE id = ?",
                      (datetime.now().isoformat(timespec="seconds"), summary[:500], sid))
            c.commit()
            c.close()
    except Exception:
        pass


def last_session_summary():
    try:
        with _lock:
            c = _conn()
            row = c.execute(
                "SELECT started_at, ended_at, summary FROM session_log "
                "WHERE ended_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
            c.close()
        if not row:
            return None
        with _lock:
            c = _conn()
            actions = c.execute(
                "SELECT COUNT(*) FROM context_events WHERE timestamp >= ? AND timestamp <= ?",
                (row[0], row[1])).fetchone()[0]
            c.close()
        return {"started_at": row[0], "ended_at": row[1],
                "summary": row[2] or "", "actions": actions}
    except Exception:
        return None


def context_block(minutes: int = 60) -> str:
    events = recent_events(minutes=minutes, limit=15)
    if not events:
        return ""
    lines = ["Recent activity on the user's computer (last hour):"]
    for e in events[:10]:
        ts = e["timestamp"][11:16]
        lines.append(f"  [{ts}] {e['kind']}: {e['detail'][:80]}")
    errs = recent_errors(hours=24, limit=3)
    if errs:
        lines.append("Recent errors:")
        for e in errs:
            lines.append(f"  {e['detail'][:100]}")
    return "\n".join(lines)
