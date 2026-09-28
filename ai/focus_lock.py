"""Focus Lock — kill distracting apps for N minutes, then restore."""

from __future__ import annotations
import subprocess, threading, time
from datetime import datetime, timedelta
from logger import get_logger

log = get_logger(__name__)

DISTRACTING = ["discord.exe", "slack.exe", "telegram.exe", "whatsapp.exe",
               "steam.exe", "spotify.exe"]

_lock_thread = None
_stop = threading.Event()
_state = {"active": False, "until": None}


def _kill(name):
    try:
        subprocess.run(["taskkill", "/F", "/IM", name],
                       capture_output=True, timeout=5)
        return True
    except Exception:
        return False


def _loop(minutes):
    _state["active"] = True
    _state["until"] = (datetime.now() + timedelta(minutes=minutes)).isoformat(timespec="minutes")
    log.info("Focus lock active for %d minutes", minutes)
    end = time.time() + minutes * 60
    while time.time() < end and not _stop.is_set():
        for app in DISTRACTING:
            _kill(app)
        time.sleep(10)
    _state["active"] = False
    _state["until"] = None
    log.info("Focus lock ended")


def start(minutes=60):
    global _lock_thread
    if _state["active"]: return False
    _stop.clear()
    _lock_thread = threading.Thread(target=_loop, args=(minutes,), daemon=True)
    _lock_thread.start()
    return True


def stop():
    _stop.set()
    _state["active"] = False
    _state["until"] = None


def status():
    return dict(_state)
