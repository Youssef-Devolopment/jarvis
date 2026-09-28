"""Proactive behavior — JARVIS offers help without being asked."""
from __future__ import annotations
from datetime import datetime
from logger import get_logger

log = get_logger(__name__)


def _time_of_day() -> str:
    h = datetime.now().hour
    if h < 5:  return "evening"
    if h < 12: return "morning"
    if h < 17: return "afternoon"
    if h < 21: return "evening"
    return "night"


def startup_greeting(user_title: str = "sir") -> str:
    from memory import context
    part = _time_of_day()
    base = f"Good {part}, {user_title}."
    last = context.last_session_summary()
    recent = context.recent_events(minutes=60, limit=10)
    lines = [base]
    if last and last.get("summary"):
        ago = _humanize_time_diff(last["ended_at"])
        lines.append(f"Last time we spoke was {ago}.")
        if last.get("actions", 0) > 5:
            lines.append(f"You did {last['actions']} actions in that session.")
    elif recent:
        apps = [e for e in recent if e["kind"] == "app"]
        if apps:
            # Extract just the app name — strip "launched " / "focused "
            detail = apps[0]["detail"]
            for prefix in ("launched ", "focused "):
                if detail.startswith(prefix):
                    detail = detail[len(prefix):]
                    break
            if detail:
                lines.append(f"You've been working with {detail}.")
    errs = context.recent_errors(hours=24, limit=1)
    if errs:
        lines.append("I noticed an error earlier — want me to check it?")
    else:
        lines.append("Everything looks fine.")
    return " ".join(lines)


def _humanize_time_diff(iso_ts: str) -> str:
    try:
        then = datetime.fromisoformat(iso_ts)
        delta = datetime.now() - then
        secs = int(delta.total_seconds())
        if secs < 60:
            return "moments ago"
        if secs < 3600:
            return f"{secs // 60} minutes ago"
        if secs < 86400:
            return f"{secs // 3600} hours ago"
        if secs < 172800:
            return "yesterday"
        return f"{secs // 86400} days ago"
    except Exception:
        return "recently"


def after_action_suggestion(action: str, result: str):
    low = (result or "").lower()
    if action == "fs_read" and len(result) > 500:
        return "Want me to summarize what I read?"
    if action == "fs_write":
        return "Want me to run it?"
    if action == "term_run" and "git status" in low and "modified" in low:
        return "Want me to commit these changes?"
    if action == "term_run" and "error" in low:
        return "Want me to check the logs?"
    return None
