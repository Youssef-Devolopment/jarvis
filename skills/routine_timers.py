"""Timers and reminders."""
from __future__ import annotations
import threading, time
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _speak(msg):
    spoken = False
    try:
        from voice import speak_async
        speak_async(msg)
        spoken = True
    except Exception as exc:
        log.warning("Timer speech failed: %s", exc)
    try:
        from system import notify
        if spoken:
            from system import overlay
            overlay.notice(msg[:70])        # flash the open HUD only
        else:
            notify.alert("JARVIS Timer", msg)   # toast + HUD pulse
    except Exception as exc:
        log.warning("Timer alert failed: %s", exc)


def _fire(msg, secs):
    # Prefer the APScheduler one-shot queue; fall back to a raw thread
    # when the scheduler library isn't installed.
    try:
        import functools
        from system.scheduler import add_one_shot, is_available
        if is_available() and add_one_shot(functools.partial(_speak, msg),
                                           secs):
            return
    except Exception:
        pass
    time.sleep(secs)
    _speak(msg)


@register("timer", [
    r"^(?:set\s+(?:a\s+)?timer(?:\s+for)?|remind\s+me)\s+"
    r"(?P<n>\d+)\s*(?P<u>seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)"
    r"(?:\s+(?:to|about|for)\s+(?P<what>.+?))?[\?\.\!]?$",
], "Set timer or reminder")
def s_timer(text, m):
    n = int(m.group("n"))
    u = m.group("u").lower()
    if u.startswith("h"):
        mult, unit = 3600, "hour"
    elif u.startswith("m"):
        mult, unit = 60, "minute"
    else:
        mult, unit = 1, "second"
    seconds = n * mult
    what = (m.group("what") or "").strip()
    label = f"{n} {unit}{'s' if n != 1 else ''}"
    if what:
        msg = f"Sir, this is your reminder: {what}."
    else:
        msg = f"Sir, your {label} timer is done."
    threading.Thread(target=_fire, args=(msg, seconds), daemon=True).start()
    return f"Timer set for {label}{(' — ' + what) if what else ''}."
