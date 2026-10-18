"""Recent-turn trail — what the last commands actually did.

The audit trail (`system/audit.py`) records tool calls, consent
verdicts and mission steps. It does not record how a *turn* was
routed, which is the question a user actually asks while using the
app: did one of my skills answer that, or did it go to a model? Which
model? Why did it take two seconds? Did it fail?

That is what lives here. A bounded in-memory ring, deliberately: the
point is to make the app legible while you use it, not to archive a
history (the chat history and the audit log already do that). Served
to the dashboard by `GET /api/turns`. Nothing here ever raises.
"""
from __future__ import annotations

import threading
from collections import deque
from datetime import datetime

_KEEP = 50

_lock = threading.Lock()
_turns: deque = deque(maxlen=_KEEP)
_seq = 0


def record(text, source, ok=True, ms=None, extra=None, **fields) -> dict:
    """Append one turn and return it. Never raises.

    `source` is who answered: skill, llm, consent, auto_skill, no_key.
    `fields` are optional labels (skill, route, model, verdict, error,
    chars) merged into the entry; empty ones are dropped so entries
    stay small.
    """
    global _seq
    try:
        with _lock:
            _seq += 1
            entry = {
                "n": _seq,
                "ts": datetime.now().strftime("%H:%M:%S"),
                "text": (text or "")[:160],
                "source": str(source or "unknown"),
                "ok": bool(ok),
            }
            if ms is not None:
                entry["ms"] = int(ms)
            for key, value in list(fields.items()) + list((extra or {}).items()):
                if value not in (None, ""):
                    entry[key] = value
            _turns.append(entry)
            return entry
    except Exception:
        return {}


def recent(limit: int = 20) -> list:
    """Newest-first turns, capped. Garbage `limit` becomes the default."""
    try:
        n = max(1, min(int(limit), _KEEP))
    except (TypeError, ValueError):
        n = 20
    with _lock:
        items = list(_turns)
    return items[-n:][::-1]


def reset() -> None:
    """Forget the ring (tests)."""
    global _seq
    with _lock:
        _turns.clear()
        _seq = 0
