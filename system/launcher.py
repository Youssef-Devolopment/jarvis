"""Desktop launcher — runs JARVIS like a real Windows app."""

from __future__ import annotations
import os
import signal
import sys
import threading
import time
import webbrowser
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_flask_thread = None
_flask_started = False
_shutdown_event = threading.Event()


def _start_flask():
    """Start Flask server in a background thread."""
    global _flask_started
    if _flask_started:
        return
    try:
        from server import app
        from config import try_settings
        s = try_settings()
        host = s.host if s else "127.0.0.1"
        port = s.port if s else 5000
        log.info("Starting Flask on %s:%d", host, port)
        from system import health as _health
        _health.mark("flask", True, f"{host}:{port}")
        app.run(host=host, port=port, debug=False,
                threaded=True, use_reloader=False)
        _flask_started = True
    except Exception as exc:
        log.exception("Flask failed: %s", exc)
        try:
            from system import health as _health
            _health.mark("flask", False, str(exc)[:120])
        except Exception:
            pass


def start_background():
    """Start Flask in background thread — non-blocking.

    Returns the service-boot summary ({"launched", "failed", ...}) so
    callers can toast the boot verdict; None when boot itself raised.
    """
    global _flask_thread
    if _flask_thread and _flask_thread.is_alive():
        return None
    _flask_thread = threading.Thread(
        target=_start_flask, name="flask", daemon=True)
    _flask_thread.start()
    # Every subsystem — voice, browser, background tasks, MCP, app
    # learner, hotkeys, tray, overlay — boots through the shared
    # registry, the same code path run.py uses, so console and
    # desktop mode can never drift apart again.
    from system import services
    summary = services.boot(mode="desktop")
    # Health glance in the log once async services settle (~20s); the
    # deferred toast only fires when something actually failed.
    try:
        from server import schedule_health_log
        from system import startup as _startup
        schedule_health_log(on_summary=_startup.toast_if_degraded)
    except Exception as exc:
        log.debug("Health log not scheduled: %s", exc)
    # Give it a moment to bind the port
    time.sleep(1.5)
    return summary


def open_jarvis_window(new_window: bool = False):
    """Open JARVIS in the default browser (or focus existing tab).

    new_window=True opens a FRESH browser window (URL in a new tab
    of that window) — used for login autostart.
    """
    try:
        from config import try_settings
        s = try_settings()
        host = s.host if s else "127.0.0.1"
        port = s.port if s else 5000
        url = f"http://{host}:{port}/"
        # webbrowser: new=0 same window, new=1 new window, new=2 new tab.
        webbrowser.open(url, new=1 if new_window else 0, autoraise=True)
    except Exception as exc:
        log.warning("Could not open JARVIS: %s", exc)


def stop_all():
    """Signal shutdown."""
    log.info("Shutdown requested")
    _shutdown_event.set()


def wait():
    """Block until shutdown."""
    try:
        while not _shutdown_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass


def _system_uptime() -> str:
    """How long the PC has been on, as a short human string."""
    try:
        import psutil
        import time as _t
        secs = int(_t.time() - psutil.boot_time())
    except Exception:
        try:
            import ctypes
            ms = ctypes.windll.kernel32.GetTickCount64()
            secs = int(ms // 1000)
        except Exception:
            return "some time"
    if secs < 90:
        return f"{secs} seconds"
    mins = secs // 60
    if mins < 90:
        return f"{mins} minute" + ("s" if mins != 1 else "")
    hrs = mins // 60
    if hrs < 48:
        rest = mins % 60
        out = f"{hrs} hour" + ("s" if hrs != 1 else "")
        if rest:
            out += f" and {rest} minute" + ("s" if rest != 1 else "")
        return out
    return f"{hrs // 24} day" + ("s" if hrs // 24 != 1 else "")


def _welcome_message() -> str:
    """Short spoken + toasted boot greeting with system uptime."""
    import datetime as _dt
    h = _dt.datetime.now().hour
    daypart = ("morning" if h < 12 else "afternoon" if h < 18 else "evening")
    return (f"Good {daypart}, sir. JARVIS is online. "
            f"The system has been up for {_system_uptime()}.")  # noqa: E501


def run_desktop_mode(open_browser: bool = False):
    """Full desktop mode: background Flask + tray + hotkey.

    open_browser=True also opens a fresh browser window once the
    server is up (used for Windows login autostart).
    """
    log.info("Starting JARVIS in desktop mode")
    from system import singleton
    if not singleton.acquire():
        log.warning("Duplicate desktop boot refused — already running.")
        return
    summary = start_background() or {}

    # Boot greeting: toast always (with the honest boot verdict —
    # skills-only and safe-mode states are said out loud), spoken
    # welcome best-effort.
    try:
        from system import notify, startup as _startup
        has_key = True
        try:
            from config import try_settings
            s = try_settings()
            has_key = bool(s and getattr(s, "has_key", False))
        except Exception:
            pass
        notify.toast("JARVIS is running",
                     _startup.toast_status(summary.get("failed"),
                                            has_key=has_key))
    except Exception:
        pass
    try:
        msg = _welcome_message()
        try:
            from voice import speak_async
            speak_async(msg)
        except Exception as exc:
            log.debug("Boot welcome speech skipped: %s", exc)
        try:
            from system import notify as _n
            _n.toast("Welcome back, sir", msg)
        except Exception:
            pass
        log.info("Boot welcome: %s", msg)
    except Exception as exc:
        log.debug("Boot welcome failed: %s", exc)

    if open_browser:
        open_jarvis_window(new_window=True)

    wait()
