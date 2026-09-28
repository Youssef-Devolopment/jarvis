"""SQLite memory: facts (long-term) + messages + sessions (chat history)."""
from __future__ import annotations
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from logger import get_logger

log = get_logger(__name__)
_DB_PATH = Path(__file__).resolve().parent / "jarvis_memory.db"
_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        with _lock:
            if _conn is None:
                _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
                _conn.execute("""CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact TEXT NOT NULL,
                    category TEXT DEFAULT 'general',
                    created_at TEXT NOT NULL,
                    source TEXT DEFAULT 'chat')""")
                _conn.execute("""CREATE TABLE IF NOT EXISTS preferences (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL)""")
                _conn.execute("""CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL)""")
                _conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_session "
                              "ON messages(session, id DESC)")
                _conn.execute("""CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL)""")
                try:
                    _conn.execute("ALTER TABLE facts ADD COLUMN "
                                  "status TEXT DEFAULT 'active'")
                except Exception:
                    pass  # column already exists
                _conn.commit()
                log.info("Memory store ready at %s", _DB_PATH)
    return _conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------- FACTS (long-term, separate from chat) ----------
def _words(s: str) -> set:
    import re
    return set(w for w in re.findall(r"[a-z0-9']+", s.lower()) if len(w) > 2)


def _similar(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _active_facts():
    c = _get_conn()
    with _lock:
        return c.execute(
            "SELECT id, fact, category FROM facts "
            "WHERE status IS NULL OR status = 'active'").fetchall()


def remember(fact: str, category: str = "general", source: str = "chat") -> int:
    fact = (fact or "").strip()
    if not fact or len(fact) < 3:
        return 0
    category = (category or "general").strip() or "general"
    # Dedup: skip near-identical facts; supersede same-topic older ones.
    best_id, best_sim, best_cat = 0, 0.0, ""
    for fid, ftext, fcat in _active_facts():
        sim = _similar(fact, ftext or "")
        if sim > best_sim:
            best_id, best_sim, best_cat = fid, sim, (fcat or "")
    if best_sim >= 0.85:
        log.debug("remember: duplicate skipped (id=%d)", best_id)
        return best_id
    c = _get_conn()
    with _lock:
        if best_sim >= 0.5 and best_cat.lower() == category.lower():
            c.execute("UPDATE facts SET status = 'replaced' WHERE id = ?",
                      (best_id,))
            log.info("remember: superseded fact id=%d", best_id)
        cur = c.execute(
            "INSERT INTO facts (fact, category, created_at, source, status) "
            "VALUES (?,?,?,?, 'active')",
            (fact, category, _now(), source))
        c.commit()
        return cur.lastrowid or 0


def _score(fact: str, category: str, fid: int, max_id: int,
           words: list, phrase: str) -> float:
    fl, cl = (fact or "").lower(), (category or "").lower()
    s = 0.0
    if phrase and phrase in fl:
        s += 3.0
    for w in words:
        if w in fl:
            s += 1.0
        if w in cl:
            s += 0.5
    if max_id:
        s += 2.0 * (fid / max_id)  # recency
    return s


def recall(query: str, limit: int = 8) -> list[dict]:
    q = (query or "").strip().lower()
    c = _get_conn()
    with _lock:
        if q:
            words = [w for w in _words(q)] or [q]
            conds, params = [], []
            for w in words:
                conds.append("(lower(fact) LIKE ? OR lower(category) LIKE ?)")
                params += [f"%{w}%", f"%{w}%"]
            rows = c.execute(
                "SELECT id, fact, category, created_at FROM facts "
                "WHERE (status IS NULL OR status = 'active') AND ("
                + " OR ".join(conds) + ") "
                "ORDER BY id DESC LIMIT 50",
                params).fetchall()
        else:
            rows = c.execute(
                "SELECT id, fact, category, created_at FROM facts "
                "WHERE status IS NULL OR status = 'active' "
                "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    if not q:
        return [{"id": r[0], "fact": r[1], "category": r[2], "created_at": r[3]}
                for r in rows]
    words = [w for w in _words(q)]
    max_id = max((r[0] for r in rows), default=0)
    scored = sorted(
        ((_score(r[1], r[2], r[0], max_id, words, q), r) for r in rows),
        key=lambda t: t[0], reverse=True)
    return [{"id": r[0], "fact": r[1], "category": r[2], "created_at": r[3]}
            for _, r in scored[:limit]]


def all_facts(limit: int = 100) -> list[dict]:
    return recall("", limit)


def forget(pattern: str) -> int:
    p = (pattern or "").strip().lower()
    if not p:
        return 0
    c = _get_conn()
    with _lock:
        cur = c.execute("DELETE FROM facts WHERE lower(fact) LIKE ?",
                        (f"%{p}%",))
        c.commit()
        return cur.rowcount


def forget_all() -> int:
    c = _get_conn()
    with _lock:
        cur = c.execute("DELETE FROM facts")
        c.commit()
        return cur.rowcount


def facts_block(limit: int = 12) -> str:
    facts = all_facts(limit=limit)
    if not facts:
        return ""
    lines = ["Things you know about the user:"]
    for f in facts:
        lines.append(f"- [{f['category']}] {f['fact']}")
    return "\n".join(lines)


# ---------- SESSIONS ----------
def ensure_session(session: str, title: str = "") -> None:
    if not session:
        return
    c = _get_conn()
    with _lock:
        row = c.execute("SELECT id FROM sessions WHERE id = ?",
                        (session,)).fetchone()
        if row is None:
            c.execute(
                "INSERT INTO sessions (id, title, created_at, updated_at) "
                "VALUES (?,?,?,?)",
                (session, title or "New chat", _now(), _now()))
        else:
            c.execute("UPDATE sessions SET updated_at = ? WHERE id = ?",
                      (_now(), session))
        c.commit()


def delete_session(session: str) -> dict:
    if not session:
        return {"error": "Missing session."}
    c = _get_conn()
    with _lock:
        m = c.execute("DELETE FROM messages WHERE session = ?",
                      (session,)).rowcount
        s = c.execute("DELETE FROM sessions WHERE id = ?",
                      (session,)).rowcount
        c.commit()
    return {"ok": True, "messages_deleted": m, "session_deleted": s > 0}


# ---------- MESSAGES ----------
def save_message(session: str, role: str, content: str) -> None:
    if not session or not role or not content:
        return
    ensure_session(session)
    c = _get_conn()
    with _lock:
        c.execute(
            "INSERT INTO messages (session, role, content, created_at) "
            "VALUES (?,?,?,?)",
            (session, role, content.strip(), _now()))
        # Auto-title from first user message
        row = c.execute(
            "SELECT title FROM sessions WHERE id = ?", (session,)).fetchone()
        if row and (not row[0] or row[0] == "New chat") and role == "user":
            c.execute("UPDATE sessions SET title = ? WHERE id = ?",
                      (content.strip()[:60], session))
        c.execute("UPDATE sessions SET updated_at = ? WHERE id = ?",
                  (_now(), session))
        c.commit()


def load_recent_messages(session: str, limit: int = 20) -> list[dict]:
    if not session:
        return []
    c = _get_conn()
    with _lock:
        rows = c.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE session = ? ORDER BY id DESC LIMIT ?",
            (session, limit)).fetchall()
    rows.reverse()
    return [{"role": r[0], "content": r[1], "created_at": r[2]}
            for r in rows]


def load_full_session(session: str) -> list[dict]:
    if not session:
        return []
    c = _get_conn()
    with _lock:
        rows = c.execute(
            "SELECT role, content, created_at FROM messages "
            "WHERE session = ? ORDER BY id ASC", (session,)).fetchall()
    return [{"role": r[0], "content": r[1], "created_at": r[2]}
            for r in rows]


def clear_session(session: str) -> int:
    if not session:
        return 0
    # Distill durable facts BEFORE wiping the transcript (background).
    try:
        msgs = load_full_session(session)
        if len(msgs) >= 2:
            import threading

            def _summarize():
                try:
                    from memory.extractor import summarize_and_store
                    summarize_and_store(msgs)
                except Exception:
                    pass
            threading.Thread(target=_summarize, daemon=True).start()
    except Exception:
        pass
    c = _get_conn()
    with _lock:
        cur = c.execute("DELETE FROM messages WHERE session = ?", (session,))
        c.commit()
        return cur.rowcount


def all_sessions(limit: int = 100) -> list[dict]:
    c = _get_conn()
    with _lock:
        rows = c.execute(
            "SELECT s.id, s.title, s.updated_at, "
            "(SELECT COUNT(*) FROM messages WHERE session = s.id) as cnt "
            "FROM sessions s ORDER BY s.updated_at DESC LIMIT ?",
            (limit,)).fetchall()
    return [{"id": r[0], "title": r[1], "updated_at": r[2], "count": r[3]}
            for r in rows]
