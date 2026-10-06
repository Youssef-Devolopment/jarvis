"""System Guard — RAM watchdog that warns before Windows does.

Samples memory once a minute; when usage crosses the threshold it
fires ONE desktop alert (with the top offender named), then stays
quiet until usage drops back down (hysteresis) so it never spams.
Everything is pref-gated: `guard_enabled` (default on) and
`guard_ram_threshold` (default 90%). Cheap by design — one
psutil call per minute, the process scan only happens when firing.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from logger import get_logger

log = get_logger("guard")

_interval = 60.0
_rearm_below = 5  # percentage points under threshold to re-arm
_thread: Optional[threading.Thread] = None
_stop = threading.Event()
_armed = True
_last: Dict[str, Any] = {}
_fired_count = 0


def _prefs() -> tuple[bool, int]:
    try:
        from memory import get_pref
        enabled = bool(get_pref("guard_enabled", True))
        threshold = int(get_pref("guard_ram_threshold", 90) or 90)
    except Exception:
        enabled, threshold = True, 90
    return enabled, max(50, min(99, threshold))


def sample() -> Dict[str, Any]:
    """One cheap memory snapshot."""
    import psutil
    vm = psutil.virtual_memory()
    out = {
        "percent": vm.percent,
        "used_gb": round(vm.total * vm.percent / 100 / 1e9, 1),
        "total_gb": round(vm.total / 1e9, 1),
        "free_gb": round(vm.available / 1e9, 1),
        "cpu": psutil.cpu_percent(interval=None),
    }
    return out


def top_consumer(min_mb: float = 200.0) -> Optional[tuple]:
    """(name, mb) of the hungriest process — only called when firing."""
    try:
        import psutil
        best = None
        for p in psutil.process_iter(["name", "memory_info"]):
            try:
                mb = p.info["memory_info"].rss / 1e6
                if mb >= min_mb and (best is None or mb > best[1]):
                    best = (p.info["name"] or "?", round(mb))
            except Exception:
                continue
        return best
    except Exception:
        return None


def _should_fire(pct: int, threshold: int) -> bool:
    global _armed, _fired_count
    if _armed and pct >= threshold:
        _armed = False
        _fired_count += 1
        return True
    if not _armed and pct < threshold - _rearm_below:
        _armed = True
    return False


def run_once(notify_fn=None) -> Optional[str]:
    """Sample + evaluate + maybe alert. Returns the alert text if fired."""
    enabled, threshold = _prefs()
    if not enabled:
        return None
    s = sample()
    _last.update(s)
    if not _should_fire(int(s["percent"]), threshold):
        return None
    hog = top_consumer()
    hog_txt = ""
    if hog:
        hog_txt = f" — {hog[0]} at {hog[1]} MB"
    msg = (f"RAM at {s['percent']}% ({s['used_gb']} of {s['total_gb']} GB)"
           f"{hog_txt}. {s['free_gb']} GB free.")
    if notify_fn is None:
        try:
            from system import notify
            notify_fn = notify.alert
        except Exception:
            notify_fn = None
    if notify_fn:
        try:
            notify_fn("Memory guard", msg)
        except Exception as exc:
            log.debug("guard alert failed: %s", exc)
    log.warning("Memory guard fired: %s", msg)
    return msg


def _loop() -> None:
    while not _stop.wait(_interval):
        try:
            run_once()
        except Exception as exc:
            log.debug("guard sample failed: %s", exc)


def start() -> bool:
    global _thread
    if _thread and _thread.is_alive():
        return False
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="guard", daemon=True)
    _thread.start()
    log.info("Memory guard started (every %ss)", int(_interval))
    return True


def stop() -> None:
    _stop.set()


def status() -> Dict[str, Any]:
    """Current state for the skill / API."""
    enabled, threshold = _prefs()
    try:
        s = dict(_last) if _last else sample()
    except Exception:
        s = {}
    s.update({"enabled": enabled, "threshold": threshold,
              "armed": _armed, "fired": _fired_count})
    return s
