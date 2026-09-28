"""Reminder loop — fires due reminders via Ryan."""

from __future__ import annotations
import threading
from logger import get_logger

log = get_logger(__name__)
_thread = None
_stop = threading.Event()


def _loop():
    log.info("Reminder loop started")
    while not _stop.is_set():
        try:
            from memory import due_reminders, mark_reminder_fired
            from voice import speak_async
            for r in due_reminders():
                log.info("Firing reminder %d: %s", r["id"], r["text"][:60])
                try: speak_async(f"Reminder, sir: {r['text']}")
                except Exception: pass
                try:
                    from system import notify
                    notify.toast("JARVIS Reminder", r["text"][:200])
                except Exception:
                    pass
                mark_reminder_fired(r["id"])
        except Exception as exc:
            log.debug("Reminder loop error: %s", exc)
        _stop.wait(30)


def start():
    global _thread
    if _thread and _thread.is_alive(): return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="reminders", daemon=True)
    _thread.start()


def stop(): _stop.set()
