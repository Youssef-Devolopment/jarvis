"""Service registry — one boot path for every background subsystem.

run.py (console) and system/launcher.py (desktop) used to start their
OWN overlapping sets of services with copy-pasted try/except blocks:
console started reminders/scheduler/dream/clipboard/MCP but desktop
did not, and failures only showed up as scattered log lines.

This registry fixes that:
  - declarative ServiceSpecs grouped core / background / voice /
    browser / mcp / desktop, with optional pref gates,
  - boot(mode) starts the set for that mode and NEVER raises,
  - every service is timed and isolated — one crash degrades that
    row only, reported in the boot summary and via health.mark(),
  - results() feeds /api/health and the Settings SYSTEM tab.

Starters are lazy imports so a missing optional dependency fails one
service, not the boot.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from logger import get_logger

log = get_logger("services")

GROUPS = ("core", "background", "voice", "browser", "mcp", "desktop")


@dataclass
class ServiceSpec:
    """One startable subsystem.

    start: may raise; returns an optional detail string.
           Return value False means "did not start" (recorded failed).
    pref:  optional memory pref key gating the service.
    threaded: run in a daemon thread (non-blocking boot; results land
           asynchronously in results()).
    detail: static hint shown until/unless the starter returns one.
    """
    name: str
    group: str
    start: Callable[[], Any]
    pref: Optional[str] = None
    pref_default: bool = True
    threaded: bool = False
    detail: str = ""


_lock = threading.Lock()
_results: Dict[str, Dict[str, Any]] = {}


def results() -> Dict[str, Dict[str, Any]]:
    """Snapshot of every recorded service result (name -> {ok, detail, ms, group})."""
    with _lock:
        return {k: dict(v) for k, v in _results.items()}


def reset() -> None:
    """Forget recorded results (tests)."""
    with _lock:
        _results.clear()


def _record(name: str, group: str, ok: bool, detail: str, ms: int) -> None:
    with _lock:
        _results[name] = {"ok": bool(ok), "detail": str(detail)[:200],
                          "ms": int(ms), "group": group}
    try:
        from system import health
        health.mark(name, ok, detail)
    except Exception:
        pass


def _pref_allows(spec: ServiceSpec) -> bool:
    if not spec.pref:
        return True
    try:
        from memory import get_pref
        return bool(get_pref(spec.pref, spec.pref_default))
    except Exception:
        return spec.pref_default


# ---------------------------------------------------------------- starters
def _mk_starters(mode: str) -> Dict[str, Callable[[], Any]]:
    """Lazy-import starters, closed over the boot mode where it matters."""

    def updater():
        from system import updater
        updater.boot_check()
        return "check running in background"

    def guard():
        from system import guard
        guard.start()
        st = guard.status()
        return "enabled" if st.get("enabled") else "disabled by pref"

    def dream():
        from system import dream_scheduler
        dream_scheduler.start()
        return "60s loop"

    def clipboard():
        from ai import clipboard_watcher
        clipboard_watcher.start()
        return "watching"

    def reminders():
        from system import reminder_loop
        reminder_loop.start()
        return "30s loop"

    def time_tracker():
        from ai import time_tracker
        time_tracker.start()
        return "tracking"

    def scheduler():
        from system.scheduler import start
        if not start():
            raise RuntimeError(
                "scheduler unavailable (APScheduler missing or start failed)")
        return "briefings + timers"

    def sentinel():
        from skills.folder_sentinel import start_saved
        n = start_saved()
        return f"{n} folder(s) restored" if n else "idle"

    def screen_context():
        from ai import screen_context
        res = screen_context.start()
        return "disabled by pref" if res is False else "RAM-only loop"

    def voice():
        from voice import warmup
        warmup()
        return "TTS warmed"

    def browser():
        from skills.browser_agent import get_agent
        get_agent().prewarm()
        return "prewarmed"

    def mcp():
        from mcp import runtime
        summary = runtime.start_all()
        started = summary.get("started") or []
        failed = summary.get("failed") or []
        if failed:
            raise RuntimeError(
                f"{len(started)} started, {len(failed)} failed: "
                + ", ".join(str(f) for f in failed[:3]))
        return f"{len(started)} server(s) started" if started else "none enabled"

    def app_learner():
        from system import app_learner
        app_learner.warm()
        return "warmed"

    def overlay():
        from system import overlay
        overlay.ensure_started()
        return "HUD pre-warmed"

    def hotkeys():
        if mode == "desktop":
            from system import hotkey
            hotkey.start_open_jarvis()
            hotkey.start_overlay_hotkey()
            return "Ctrl+Alt+J, Alt+Space"
        from system.hotkey import start_hotkey_listener
        start_hotkey_listener()  # blocks — runs threaded, record sticks
        return "listener running"

    def tray():
        if mode == "desktop":
            from system import tray
            tray.start()
        else:
            from system.tray import start_tray
            start_tray()
        return "running"

    return {
        "updater": updater, "guard": guard, "dream": dream,
        "clipboard": clipboard, "reminders": reminders,
        "time_tracker": time_tracker, "scheduler": scheduler,
        "sentinel": sentinel, "screen_context": screen_context,
        "voice": voice, "browser": browser, "mcp": mcp,
        "app_learner": app_learner, "overlay": overlay,
        "hotkeys": hotkeys, "tray": tray,
    }


def _specs(mode: str) -> List[ServiceSpec]:
    s = _mk_starters(mode)
    specs = [
        ServiceSpec("updater", "core", s["updater"]),
        ServiceSpec("guard", "core", s["guard"]),
        ServiceSpec("scheduler", "background", s["scheduler"],
                    threaded=True),
        ServiceSpec("reminders", "background", s["reminders"],
                    threaded=True, detail="30s loop"),
        ServiceSpec("dream", "background", s["dream"],
                    threaded=True, detail="60s loop"),
        ServiceSpec("clipboard", "background", s["clipboard"],
                    threaded=True, detail="watching"),
        ServiceSpec("time_tracker", "background", s["time_tracker"],
                    threaded=True, detail="tracking"),
        ServiceSpec("folder_sentinel", "background", s["sentinel"],
                    threaded=True, detail="idle"),
        ServiceSpec("screen_context", "background", s["screen_context"],
                    threaded=True, detail="RAM-only loop"),
        ServiceSpec("voice", "voice", s["voice"], threaded=True,
                    detail="TTS warmed"),
        ServiceSpec("browser", "browser", s["browser"], threaded=True,
                    detail="prewarmed"),
        ServiceSpec("mcp", "mcp", s["mcp"], threaded=True,
                    detail="starting"),
        ServiceSpec("app_learner", "desktop", s["app_learner"],
                    threaded=True, detail="warmed"),
        ServiceSpec("hotkeys", "desktop", s["hotkeys"],
                    pref="hotkey_enabled", threaded=True,
                    detail="listener running" if mode != "desktop"
                    else "Ctrl+Alt+J, Alt+Space"),
        ServiceSpec("tray", "desktop", s["tray"],
                    pref="tray_enabled", threaded=True,
                    detail="running"),
    ]
    if mode == "desktop":
        specs.append(ServiceSpec("overlay", "desktop", s["overlay"],
                                 threaded=True, detail="HUD pre-warmed"))
    return specs


def _run(spec: ServiceSpec) -> None:
    """Start one service, recording pref-skips, results, and failures."""
    if not _pref_allows(spec):
        _record(spec.name, spec.group, True, "disabled by pref", 0)
        return
    _record(spec.name, spec.group, True, spec.detail or "starting", 0)

    def worker():
        t0 = time.time()
        try:
            out = spec.start()
            if out is False:
                _record(spec.name, spec.group, False,
                        spec.detail or "did not start",
                        int((time.time() - t0) * 1000))
                return
            detail = str(out) if out else (spec.detail or "started")
            _record(spec.name, spec.group, True, detail,
                    int((time.time() - t0) * 1000))
        except Exception as exc:
            ms = int((time.time() - t0) * 1000)
            log.warning("Service '%s' failed: %s", spec.name, exc)
            _record(spec.name, spec.group, False, str(exc)[:200], ms)

    if spec.threaded:
        threading.Thread(target=worker, name=f"svc-{spec.name}",
                         daemon=True).start()
    else:
        worker()


def boot(mode: str = "console",
         only: Optional[List[str]] = None) -> Dict[str, Any]:
    """Start every service for this mode. Never raises.

    Returns {mode, launched, failed, skipped, ms, pending} where
    failed/skipped are service names (threaded results may still be
    pending — health shows them as they land).
    """
    t0 = time.time()
    specs = _specs(mode)
    if only is not None:
        specs = [s for s in specs if s.name in only]
    failed: List[str] = []
    skipped: List[str] = []
    for spec in specs:
        try:
            _run(spec)
        except Exception as exc:  # _run itself should never raise
            log.warning("Service dispatch '%s' failed: %s", spec.name, exc)
            _record(spec.name, spec.group, False, str(exc)[:200], 0)
        snap = results().get(spec.name, {})
        if not snap.get("ok", True):
            failed.append(spec.name)
        elif snap.get("detail") == "disabled by pref":
            skipped.append(spec.name)
    ms = int((time.time() - t0) * 1000)
    summary = {"mode": mode, "launched": len(specs), "failed": failed,
               "skipped": skipped, "ms": ms}
    line = (f"booted {len(specs)} services in {ms}ms"
            + (f" — {len(failed)} degraded: " + ", ".join(failed)
               if failed else ""))
    if failed:
        log.warning("Services %s", line)
    else:
        log.info("Services %s", line)
    return summary
