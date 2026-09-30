"""Background chronological scheduler — APScheduler, thread-safe cron.

Wakes up the dead briefing prefs (briefings_enabled / briefing_hour)
and replaces raw threading.Thread timer blocks. Every import is lazy
so the module is safe even when APScheduler isn't installed — callers
get a clear False / fallback path instead of a crash.
"""
from __future__ import annotations
import threading
from datetime import datetime, timedelta
from logger import get_logger

log = get_logger(__name__)

_sched = None
_lock = threading.Lock()
_BRIEF_JOB = "morning_briefing"
_WATCH_JOB = "briefing_watcher"
_TICK_JOB = "agent_tick"


def is_available() -> bool:
    try:
        import apscheduler  # noqa: F401
        return True
    except ImportError:
        return False


def is_running() -> bool:
    return _sched is not None


def _get():
    global _sched
    with _lock:
        if _sched is None:
            from apscheduler.schedulers.background import BackgroundScheduler
            _sched = BackgroundScheduler(daemon=True)
            _sched.start()
            log.info("Scheduler started")
        return _sched


def start() -> bool:
    """Start scheduler + sync cron jobs with prefs. Safe to call twice."""
    if not is_available():
        log.warning("APScheduler not installed — background jobs disabled")
        return False
    try:
        _get()
        _sync_briefing()
        _ensure_watcher()
        _ensure_tick()
        return True
    except Exception as exc:
        log.warning("Scheduler start failed: %s", exc)
        return False


def stop() -> None:
    global _sched
    with _lock:
        if _sched is not None:
            try:
                _sched.shutdown(wait=False)
            except Exception:
                pass
            _sched = None
            log.info("Scheduler stopped")


def list_jobs() -> list:
    if _sched is None:
        return []
    try:
        return [{"id": j.id, "next": str(j.next_run_time)}
                for j in _sched.get_jobs()]
    except Exception:
        return []


def add_one_shot(func, seconds: float, job_id: str = "") -> bool:
    """Run func once after `seconds`. Used by the timer skill."""
    if not is_available():
        return False
    try:
        from apscheduler.triggers.date import DateTrigger
        s = _get()
        s.add_job(func, DateTrigger(
            run_date=datetime.now() + timedelta(seconds=max(0, seconds))),
            args=(), id=job_id or f"oneshot_{id(func)}",
            replace_existing=True, misfire_grace_time=60)
        return True
    except Exception as exc:
        log.warning("One-shot schedule failed: %s", exc)
        return False


def _sync_briefing() -> None:
    """Create/remove the daily briefing job to match current prefs."""
    try:
        from memory import get_pref
        enabled = bool(get_pref("briefings_enabled", False))
        hour = int(get_pref("briefing_hour", 8))
    except Exception:
        return
    try:
        from apscheduler.triggers.cron import CronTrigger
        s = _get()
        job = s.get_job(_BRIEF_JOB)
        if enabled:
            hour = max(0, min(23, hour))
            if job is None:
                s.add_job(_run_briefing, CronTrigger(hour=hour, minute=0),
                          id=_BRIEF_JOB, replace_existing=True,
                          misfire_grace_time=3600)
                log.info("Briefing scheduled daily at %02d:00", hour)
        elif job is not None:
            s.remove_job(_BRIEF_JOB)
            log.info("Briefing disabled, job removed")
    except Exception as exc:
        log.warning("Briefing sync failed: %s", exc)


def _ensure_watcher() -> None:
    """Every 15 min re-sync cron jobs with prefs (self-healing)."""
    try:
        s = _get()
        if s.get_job(_WATCH_JOB) is None:
            s.add_job(_sync_briefing, "interval", minutes=15,
                      id=_WATCH_JOB, replace_existing=True)
    except Exception as exc:
        log.warning("Watcher install failed: %s", exc)


def refresh() -> None:
    """Re-read prefs now (call after the user edits briefing settings)."""
    if _sched is not None:
        _sync_briefing()


def _ensure_tick() -> None:
    """Agent loop heartbeat every 15 min (self-guards on prefs)."""
    try:
        s = _get()
        if s.get_job(_TICK_JOB) is None:
            def _tick():
                try:
                    from ai.os_mode import tick
                    tick()
                except Exception as exc:
                    log.warning("Agent tick failed: %s", exc)
            s.add_job(_tick, "interval", minutes=15,
                      id=_TICK_JOB, replace_existing=True)
    except Exception as exc:
        log.warning("Tick install failed: %s", exc)


def compose_briefing() -> str:
    """Morning briefing with teeth: greeting + reminders + remembered facts."""
    from ai.proactive import startup_greeting
    from memory import get_pref
    title = get_pref("user_title", "sir") or "sir"
    parts = [startup_greeting(title).rstrip(".")]
    try:
        from memory import list_reminders
        pending = list_reminders(only_pending=True)
        if pending:
            first = pending[0]["text"][:80]
            parts.append(f"You have {len(pending)} pending reminder"
                         f"{'s' if len(pending) != 1 else ''}, "
                         f"first: {first}")
    except Exception:
        pass
    try:
        from memory import all_facts
        facts = all_facts()
        if facts:
            sample = "; ".join(str(f.get("fact", ""))[:60] for f in facts[:3])
            parts.append(f"You told me: {sample}")
    except Exception:
        pass
    return ". ".join(parts) + "."


def _run_briefing() -> None:
    try:
        msg = compose_briefing()
        log.info("Morning briefing: %r", msg[:120])
        try:
            from voice import speak_async
            speak_async("Good morning. " + msg)
        except Exception as exc:
            log.warning("Briefing speech failed: %s", exc)
        try:
            from system import notify
            notify.toast("Morning briefing", msg[:220])
        except Exception:
            pass
        try:
            from memory import context as ctx
            ctx.log_event("briefing", msg[:200])
        except Exception:
            pass
    except Exception as exc:
        log.warning("Briefing run failed: %s", exc)
