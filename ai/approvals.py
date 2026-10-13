"""Tool consent — the allow/confirm/deny permission layer.

Read-only tools run free. Anything that changes state (files,
processes, windows, third-party MCP side effects) needs the user's
word first — unless the `tool_approval` pref is "auto".

The agent loop runs inside one streaming request and cannot pause
for a click, so consent works across turns: a gated call is NOT
executed; instead it is parked as a numbered pending request and the
model asks the user in plain words.  "allow 3" / "deny 3" on the
next turn resolves it — the approved tool runs immediately and its
result comes back as the reply.  Nothing here ever raises.
"""
from __future__ import annotations
import re
import threading
import time
from logger import get_logger

log = get_logger(__name__)

# State-changing tools: parked until the user says allow.
CONFIRM_TOOLS = {
    "fs_write", "fs_append", "fs_replace", "fs_delete", "fs_mkdir",
    "term_run", "term_python",
    "win_click", "win_type", "focus_app", "launch_app",
    "bridge_transfer", "computer_run",
}

_TTL = 600.0
_CAP = 20
_REPLY_CAP = 1500

_lock = threading.Lock()
_pending: dict = {}
_next_id = 1

_APPROVAL_RE = re.compile(r"(allow|approve|deny|reject)\s+#?(\d+)\s*\.?\s*$",
                          re.IGNORECASE)


def needs_approval(name: str) -> bool:
    """True when calling `name` must park for consent first."""
    if not isinstance(name, str) or not name:
        return False
    return name in CONFIRM_TOOLS or name.startswith("mcp__")


def approval_mode() -> str:
    """'ask' (park mutations for consent) or 'auto' (run everything).
    Unknown values fail safe to 'ask'."""
    try:
        from memory import get_pref
        mode = str(get_pref("tool_approval", "ask") or "ask").lower()
    except Exception:
        return "ask"
    return "auto" if mode == "auto" else "ask"


def gate_active() -> bool:
    return approval_mode() == "ask"


def _prune_locked(now: float) -> None:
    for pid in [p for p, e in _pending.items()
                if now - e["ts"] > _TTL]:
        _pending.pop(pid, None)


def propose(tool: str, args: dict) -> int:
    """Park a gated call. Returns its request number."""
    global _next_id
    with _lock:
        now = time.time()
        _prune_locked(now)
        while len(_pending) >= _CAP:
            oldest = min(_pending, key=lambda p: _pending[p]["ts"])
            _pending.pop(oldest, None)
        pid = _next_id
        _next_id += 1
        _pending[pid] = {"tool": tool, "args": dict(args or {}), "ts": now}
        return pid


def pending_list() -> list:
    with _lock:
        _prune_locked(time.time())
        return [{"id": p, "tool": e["tool"], "args": e["args"]}
                for p, e in sorted(_pending.items())]


def _take(pid: int):
    with _lock:
        _prune_locked(time.time())
        return _pending.pop(pid, None)


def awaiting_text(tool: str, pid: int) -> str:
    return (f"[awaiting approval #{pid}: {tool} was NOT run — ask the "
            f"user in plain words to reply 'allow {pid}' to run it or "
            f"'deny {pid}' to refuse. Do NOT call it again.]")


def match_approval(text: str):
    """('allow'|'deny', number) for a verdict turn, else None."""
    m = _APPROVAL_RE.match((text or "").strip())
    if not m:
        return None
    verb = m.group(1).lower()
    return ("allow" if verb in ("allow", "approve") else "deny",
            int(m.group(2)))


def handle_approval_text(text: str):
    """Resolve one pending request and run or refuse it. Returns the
    reply, or None when `text` is not an approval verdict."""
    matched = match_approval(text)
    if not matched:
        return None
    verb, pid = matched
    entry = _take(pid)
    if entry is None:
        if pending_list():
            ids = ", ".join(f"#{p['id']}" for p in pending_list())
            return (f"Nothing is waiting under #{pid}. Open requests: "
                    f"{ids}.")
        return f"Nothing is waiting under #{pid} — no open requests."
    tool = entry["tool"]
    try:
        from system import audit as _trail
    except Exception:
        _trail = None
    if verb == "deny":
        log.info("Consent denied: %s #%d", tool, pid)
        if _trail is not None:
            try:
                _trail.record("consent_deny", tool, True, f"#{pid}")
            except Exception:
                pass
        return (f"Denied — {tool} was not run. Tell me what to do "
                f"instead, sir.")
    try:
        from ai.tools import execute_tool
        result = execute_tool(tool, entry["args"])
    except Exception as exc:
        if _trail is not None:
            try:
                _trail.record("consent_run", tool, False,
                              f"#{pid} {exc}"[:100])
            except Exception:
                pass
        return f"Approved, but running {tool} failed: {exc}"
    log.info("Consent approved: %s #%d", tool, pid)
    if _trail is not None:
        try:
            _trail.record("consent_run", tool, True, f"#{pid}")
        except Exception:
            pass
    out = str(result)
    if len(out) > _REPLY_CAP:
        out = out[:_REPLY_CAP] + "\n[…trimmed]"
    return out or "(done, no output)"
