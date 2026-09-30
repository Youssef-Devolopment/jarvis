"""Save and read notes (Obsidian vault when available, else SQLite)."""
from __future__ import annotations
import sqlite3, threading
from datetime import datetime
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_DB = Path(__file__).resolve().parent.parent / "memory" / "jarvis_memory.db"
_lock = threading.Lock()


def _obsidian():
    try:
        from ai import obsidian
        return obsidian if obsidian.is_available() else None
    except Exception:
        return None


def _conn():
    c = sqlite3.connect(str(_DB), check_same_thread=False)
    c.execute("""CREATE TABLE IF NOT EXISTS notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        content TEXT NOT NULL,
        created_at TEXT NOT NULL)""")
    c.commit()
    return c


@register("note_save", [
    r"^(?:note|remember\s+to\s+note)[:,]?\s+(?:that\s+)?(?P<n>.+?)[\?\.\!]?$",
    r"^make\s+(?:a\s+)?note[:]?\s+(?P<n2>.+?)[\?\.\!]?$",
], "Save a note")
def s_save(text, m):
    gd = m.groupdict()
    note = (gd.get("n") or gd.get("n2") or "").strip()
    if not note or len(note) < 2:
        return None
    ob = _obsidian()
    if ob:
        fn = ob.save_note(note)
        if fn:
            return f"Noted in Obsidian: {note[:80]}"
    with _lock:
        c = _conn()
        c.execute("INSERT INTO notes (content, created_at) VALUES (?,?)",
                  (note, datetime.now().isoformat(timespec="seconds")))
        c.commit()
        c.close()
    return f"Noted: {note[:80]}"


@register("note_read", [
    r"^(?:what\s+are\s+)?(?:my|the)\s+notes[\?\.\!]?$",
    r"^read\s+(?:my|the)\s+notes[\?\.\!]?$",
    r"^show\s+(?:my|the)\s+notes[\?\.\!]?$",
], "Read notes")
def s_read(text, m):
    ob = _obsidian()
    if ob:
        rows = ob.list_notes(limit=5)
        if not rows:
            return "No notes yet."
        lines = [f"Last {len(rows)} notes (Obsidian):"]
        for r in rows:
            lines.append(f"- {r['content'][:80]}")
        return " ".join(lines)
    with _lock:
        c = _conn()
        rows = c.execute("SELECT content, created_at FROM notes "
                         "ORDER BY id DESC LIMIT 5").fetchall()
        c.close()
    if not rows:
        return "No notes yet."
    lines = [f"Last {len(rows)} notes:"]
    for content, _ in rows:
        lines.append(f"- {content[:80]}")
    return " ".join(lines)


@register("note_clear", [
    r"^(?:clear|delete|erase|forget)\s+(?:all\s+)?(?:my\s+)?notes[\?\.\!]?$",
], "Clear notes")
def s_clear(text, m):
    ob = _obsidian()
    cleared_ob = ob.clear_notes() if ob else 0
    with _lock:
        c = _conn()
        n = c.execute("DELETE FROM notes").rowcount
        c.commit()
        c.close()
    return f"Cleared {n + cleared_ob} notes."
