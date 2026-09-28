"""Background scheduler for Dream Mode."""

from __future__ import annotations
import threading
import time
from datetime import datetime
from logger import get_logger

log = get_logger(__name__)

_thread = None
_stop = threading.Event()


def _in_window(start_hour: int, end_hour: int) -> bool:
    h = datetime.now().hour
    if start_hour <= end_hour:
        return start_hour <= h < end_hour
    # wraps midnight (e.g. 22 to 6)
    return h >= start_hour or h < end_hour


def _loop():
    last_run_date = None
    while not _stop.is_set():
        try:
            from memory import get_pref
            enabled = get_pref("dream_enabled", False)
            start_h = int(get_pref("dream_start_hour", 3))
            end_h = int(get_pref("dream_end_hour", 5))

            if enabled and _in_window(start_h, end_h):
                today = datetime.now().date()
                if last_run_date != today:
                    log.info("Dream Mode: window active, running now")
                    try:
                        from ai import dream_mode
                        dream_mode.run_dream()
                    except Exception as exc:
                        log.exception("Dream run failed: %s", exc)
                    last_run_date = today
        except Exception as exc:
            log.debug("Dream loop error: %s", exc)

        # Check every 60 seconds
        _stop.wait(60)


def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="dream", daemon=True)
    _thread.start()
    log.info("Dream scheduler started")


def stop():
    _stop.set()
    log.info("Dream scheduler stopped")
