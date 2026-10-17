"""Agent audit trail — one append-only log for every agent action.

Chat-loop tool calls, consent approvals/denials and OS-mission steps
all land here in the same line format, so a user (or test) can answer
"what ran, what was denied, and why" from a single file.  Served to
the dashboard via GET /api/audit (tail only, never the whole file).
Nothing here ever raises.
"""
from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_FILE = _ROOT / "logs" / "code_mode_audit.log"
_MAX_TAIL = 200

_lock = threading.Lock()


def record(action: str, target: str, ok: bool = True,
           extra: str = "") -> None:
    """Append one audit line. Never raises."""
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        line = (f"[{ts}] {'OK' if ok else 'FAIL':4} {action:12} "
                f"{target} {extra}\n")
        with _lock:
            _FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_FILE, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception as exc:
        log.debug("Audit record failed: %s", exc)


def read_tail(limit: int = 50) -> list:
    """Newest-first audit lines (capped). Missing file => []."""
    try:
        n = int(limit)
    except (TypeError, ValueError):
        n = 50
    n = max(1, min(n, _MAX_TAIL))
    try:
        with _lock:
            text = _FILE.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    except Exception as exc:
        log.debug("Audit read failed: %s", exc)
        return []
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return lines[-n:][::-1]
