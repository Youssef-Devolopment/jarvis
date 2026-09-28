"""Outcome memory — track replies, detect rejections, learn."""

from __future__ import annotations
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_DB = Path(__file__).resolve().parent / "jarvis_memory.db"
_lock = threading.Lock()

REJECTION_PATTERNS = [
    r"^\s*(?:no|nope|nah|wrong|incorrect|not that)\b",
    r"\b(?:that'?s\s+wrong|that is wrong)\b",
    r"\b(?:لأ|لا|غلط|مش كده|مش ده)\b",
    r"\b(?:not\s+what\s+i\s+(?:want|asked|meant))\b",
    r"\b(?:try\s+again|redo|start\s+over)\b",
    r"\b(?:bad\s+answer|wrong\s+answer)\b",
]

CONFIRMATION_PATTERNS = [
    r"^\s*(?:yes|yep|yeah|correct|exactly|perfect|great|thanks)\b",
    r"\b(?:that'?s\s+(?:right|correct))\b",
    r"\b(?:أيوه|تمام|صح|مظبوط)\b",
]

_REJECT = [re.compile(p, re.IGNORECASE) for p in REJECTION_PATTERNS]
_CONFIRM = [re.compile(p, re.IGNORECASE) for p in CONFIRMATION_PATTERNS]


def _conn():
    c = sqlite3.connect(str(_DB), check_same_thread=False)
    c.execute("""CREATE TABLE IF NOT EXISTS outcomes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        accepted INTEGER DEFAULT NULL,
        feedback TEXT DEFAULT '',
        created_at TEXT NOT NULL)""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_accepted "
              "ON outcomes(accepted)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_outcomes_created "
              "ON outcomes(created_at DESC)")
    c.commit()
    return c


def record(question: str, answer: str) -> int:
    """Record a JARVIS reply. Returns outcome id."""
    if not question or not answer:
        return 0
    try:
        with _lock:
            c = _conn()
            cur = c.execute(
                "INSERT INTO outcomes (question, answer, created_at) "
                "VALUES (?,?,?)",
                (question[:500], answer[:2000],
                 datetime.now().isoformat(timespec="seconds")))
            c.commit()
            oid = cur.lastrowid or 0
            c.close()
            return oid
    except Exception as exc:
        log.debug("Outcome record failed: %s", exc)
        return 0


def detect_rejection(text: str) -> bool:
    """Is the user rejecting the last answer?"""
    if not text:
        return False
    for pat in _REJECT:
        if pat.search(text):
            return True
    return False


def detect_confirmation(text: str) -> bool:
    if not text:
        return False
    for pat in _CONFIRM:
        if pat.search(text):
            return True
    return False


def update_last(accepted: bool, feedback: str = "") -> int:
    """Mark the most recent outcome as accepted or rejected."""
    try:
        with _lock:
            c = _conn()
            row = c.execute(
                "SELECT id FROM outcomes WHERE accepted IS NULL "
                "ORDER BY id DESC LIMIT 1").fetchone()
            if not row:
                c.close()
                return 0
            oid = row[0]
            c.execute(
                "UPDATE outcomes SET accepted = ?, feedback = ? WHERE id = ?",
                (1 if accepted else 0, feedback[:300], oid))
            c.commit()
            c.close()
            log.info("Outcome %d marked %s",
                     oid, "accepted" if accepted else "rejected")
            return oid
    except Exception as exc:
        log.debug("Outcome update failed: %s", exc)
        return 0


def recent_rejected(limit: int = 5) -> list:
    """Recent rejected answers (to avoid repeating)."""
    try:
        with _lock:
            c = _conn()
            rows = c.execute(
                "SELECT question, answer, feedback FROM outcomes "
                "WHERE accepted = 0 ORDER BY id DESC LIMIT ?",
                (limit,)).fetchall()
            c.close()
        return [{"question": r[0], "answer": r[1], "feedback": r[2]}
                for r in rows]
    except Exception:
        return []


def rejection_block(limit: int = 5) -> str:
    """Compact block for the system prompt."""
    rejected = recent_rejected(limit=limit)
    if not rejected:
        return ""
    lines = ["Previously rejected answers — do NOT repeat these:"]
    for r in rejected:
        q = r["question"][:80]
        a = r["answer"][:120]
        fb = r.get("feedback", "")
        line = f"- Q: {q}\n  A: {a}"
        if fb:
            line += f"\n  User said: {fb}"
        lines.append(line)
    return "\n".join(lines)


def stats() -> dict:
    try:
        with _lock:
            c = _conn()
            total = c.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
            accepted = c.execute(
                "SELECT COUNT(*) FROM outcomes WHERE accepted = 1").fetchone()[0]
            rejected = c.execute(
                "SELECT COUNT(*) FROM outcomes WHERE accepted = 0").fetchone()[0]
            pending = c.execute(
                "SELECT COUNT(*) FROM outcomes WHERE accepted IS NULL").fetchone()[0]
            c.close()
        return {"total": total, "accepted": accepted,
                "rejected": rejected, "pending": pending}
    except Exception:
        return {"total": 0, "accepted": 0, "rejected": 0, "pending": 0}
