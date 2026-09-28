"""Time tracker — log foreground window every 30s."""

from __future__ import annotations
import platform, threading, time
from logger import get_logger

log = get_logger(__name__)
IS_WIN = platform.system() == "Windows"

_thread = None
_stop = threading.Event()
_last = {"app": "", "since": 0.0}


def _foreground():
    if not IS_WIN: return ("", "")
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        try:
            import psutil
            proc = psutil.Process(pid.value)
            return (proc.name(), title)
        except Exception:
            return ("unknown", title)
    except Exception:
        return ("", "")


def _loop():
    log.info("Time tracker started")
    while not _stop.is_set():
        try:
            app, title = _foreground()
            if app:
                if app != _last["app"]:
                    if _last["app"] and _last["since"]:
                        dur = int(time.time() - _last["since"])
                        if dur >= 5:
                            try:
                                from memory import log_time_entry
                                log_time_entry(_last["app"], "", dur)
                            except Exception: pass
                    _last["app"] = app
                    _last["since"] = time.time()
        except Exception as exc:
            log.debug("Time tracker error: %s", exc)
        _stop.wait(30)


def start():
    global _thread
    if _thread and _thread.is_alive(): return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="time_tracker", daemon=True)
    _thread.start()


def stop(): _stop.set()


def summary(hours=24):
    from memory import time_summary
    return time_summary(hours=hours)
