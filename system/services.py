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
    stop:  optional synchronous stop handler (loop watchers, schedulers,
           MCP servers). None = one-shot warmup or boot-only listener
           that cannot be safely cycled at runtime.
    restartable: False for boot-only listeners (hotkeys, tray) where a
           second start would race/duplicate the first.
    """
    name: str
    group: str
    start: Callable[[], Any]
    pref: Optional[str] = None
    pref_default: bool = True
    threaded: bool = False
    detail: str = ""
    stop: Optional[Callable[[], Any]] = None
    restartable: bool = True


_lock = threading.Lock()
_results: Dict[str, Dict[str, Any]] = {}
_booted_mode: Optional[str] = None  # set by boot(); guides _find_spec


def results() -> Dict[str, Dict[str, Any]]:
    """Snapshot of every recorded service result (name -> {ok, detail, ms, group})."""
    with _lock:
        return {k: dict(v) for k, v in _results.items()}


def reset() -> None:
    """Forget recorded results (tests)."""
    with _lock:
        _results.clear()


def _record(name: str, group: str, ok: bool, detail: str, ms: int,
            spec: Optional[ServiceSpec] = None) -> None:
    with _lock:
        rec = {"ok": bool(ok), "detail": str(detail)[:200],
               "ms": int(ms), "group": group}
        if spec is not None:  # control flags for the SYSTEM tab buttons
            rec["stoppable"] = spec.stop is not None
            rec["restartable"] = bool(spec.restartable)
        _results[name] = rec
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


# --------------------------------------------------------------- stoppers
def _mk_stoppers() -> Dict[str, Callable[[], Any]]:
    """Lazy-import stop handlers (sync, safe to call when not running).

    Only services with a verified stop -> start cycle appear here; warmup
    one-shots (voice/browser/updater/app_learner) and boot-only listeners
    (hotkeys/tray) have no stop handler and refuse runtime cycling.
    """

    def reminders():
        from system import reminder_loop
        reminder_loop.stop()

    def dream():
        from system import dream_scheduler
        dream_scheduler.stop()

    def scheduler():
        from system.scheduler import stop
        stop()

    def guard():
        from system import guard
        guard.stop()

    def clipboard():
        from ai import clipboard_watcher
        clipboard_watcher.stop()

    def time_tracker():
        from ai import time_tracker
        time_tracker.stop()

    def screen_context():
        from ai import screen_context
        screen_context.stop()

    def mcp():
        from mcp import runtime
        names = runtime.running_names()
        stopped = 0
        for n in names:
            try:
                if runtime.stop_server(n):
                    stopped += 1
            except Exception:
                continue
        return f"stopped {stopped} server(s)"

    def sentinel():
        from skills.folder_sentinel import unwatch
        unwatch("")  # empty path = stop every watch

    return {
        "reminders": reminders, "dream": dream, "scheduler": scheduler,
        "guard": guard, "clipboard": clipboard,
        "time_tracker": time_tracker, "screen_context": screen_context,
        "mcp": mcp, "folder_sentinel": sentinel,
    }


def _specs(mode: str) -> List[ServiceSpec]:
    s = _mk_starters(mode)
    p = _mk_stoppers()
    specs = [
        ServiceSpec("updater", "core", s["updater"]),
        ServiceSpec("guard", "core", s["guard"], stop=p["guard"]),
        ServiceSpec("scheduler", "background", s["scheduler"],
                    threaded=True, stop=p["scheduler"]),
        ServiceSpec("reminders", "background", s["reminders"],
                    threaded=True, detail="30s loop",
                    stop=p["reminders"]),
        ServiceSpec("dream", "background", s["dream"],
                    threaded=True, detail="60s loop", stop=p["dream"]),
        ServiceSpec("clipboard", "background", s["clipboard"],
                    threaded=True, detail="watching",
                    stop=p["clipboard"]),
        ServiceSpec("time_tracker", "background", s["time_tracker"],
                    threaded=True, detail="tracking",
                    stop=p["time_tracker"]),
        ServiceSpec("folder_sentinel", "background", s["sentinel"],
                    threaded=True, detail="idle",
                    stop=p["folder_sentinel"]),
        ServiceSpec("screen_context", "background", s["screen_context"],
                    threaded=True, detail="RAM-only loop",
                    stop=p["screen_context"]),
        ServiceSpec("voice", "voice", s["voice"], threaded=True,
                    detail="TTS warmed"),
        ServiceSpec("browser", "browser", s["browser"], threaded=True,
                    detail="prewarmed"),
        ServiceSpec("mcp", "mcp", s["mcp"], threaded=True,
                    detail="starting", stop=p["mcp"]),
        ServiceSpec("app_learner", "desktop", s["app_learner"],
                    threaded=True, detail="warmed"),
        ServiceSpec("hotkeys", "desktop", s["hotkeys"],
                    pref="hotkey_enabled", threaded=True, restartable=False,
                    detail="listener running" if mode != "desktop"
                    else "Ctrl+Alt+J, Alt+Space"),
        ServiceSpec("tray", "desktop", s["tray"],
                    pref="tray_enabled", threaded=True, restartable=False,
                    detail="running"),
    ]
    if mode == "desktop":
        specs.append(ServiceSpec("overlay", "desktop", s["overlay"],
                                 threaded=True, detail="HUD pre-warmed"))
    return specs


def _run(spec: ServiceSpec) -> None:
    """Start one service, recording pref-skips, results, and failures."""
    if not _pref_allows(spec):
        _record(spec.name, spec.group, True, "disabled by pref", 0, spec)
        return
    _record(spec.name, spec.group, True, spec.detail or "starting", 0, spec)

    def worker():
        t0 = time.time()
        try:
            out = spec.start()
            if out is False:
                _record(spec.name, spec.group, False,
                        spec.detail or "did not start",
                        int((time.time() - t0) * 1000), spec)
                return
            detail = str(out) if out else (spec.detail or "started")
            _record(spec.name, spec.group, True, detail,
                    int((time.time() - t0) * 1000), spec)
        except Exception as exc:
            ms = int((time.time() - t0) * 1000)
            log.warning("Service '%s' failed: %s", spec.name, exc)
            _record(spec.name, spec.group, False, str(exc)[:200], ms, spec)

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
    global _booted_mode
    t0 = time.time()
    _booted_mode = mode  # stop/restart resolve specs against this mode
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
            _record(spec.name, spec.group, False, str(exc)[:200], 0, spec)
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


# --------------------------------------------------------------- control
def _find_spec(name: str) -> Optional[ServiceSpec]:
    """Locate a spec by name across boot modes (booted mode first)."""
    modes = ["console", "desktop"]
    if _booted_mode in modes:
        modes = [_booted_mode] + [m for m in modes if m != _booted_mode]
    for mode in modes:
        for spec in _specs(mode):
            if spec.name == name:
                return spec
    return None


def describe(name: str) -> Optional[Dict[str, Any]]:
    """Control metadata + current state for one service (None = unknown)."""
    spec = _find_spec(name)
    if spec is None:
        return None
    cur = results().get(name, {})
    return {"name": spec.name, "group": spec.group,
            "stoppable": spec.stop is not None,
            "restartable": spec.restartable,
            "ok": cur.get("ok"), "detail": cur.get("detail", ""),
            "ms": cur.get("ms", 0)}


def stop_service(name: str) -> Dict[str, Any]:
    """Run a service's stop handler, recording 'stopped'. Raises for
    unknown names or services without a stop handler; a handler that
    fails records the failure and returns it (ok=False)."""
    spec = _find_spec(name)
    if spec is None:
        raise ValueError(f"unknown service '{name}'")
    if spec.stop is None:
        raise ValueError(f"service '{name}' has no stop handler "
                         "(one-shot warmup or boot-only listener)")
    t0 = time.time()
    try:
        out = spec.stop()
        detail = str(out) if out else "stopped"
        _record(name, spec.group, True, detail,
                int((time.time() - t0) * 1000), spec)
        log.info("Service '%s' stopped", name)
    except Exception as exc:
        log.warning("Stop of '%s' failed: %s", name, exc)
        _record(name, spec.group, False, f"stop failed: {exc}"[:200],
                int((time.time() - t0) * 1000), spec)
    return results().get(name, {})


def restart(name: str) -> Dict[str, Any]:
    """Stop (when a handler exists) then start the service again.

    A failed stop does not abort the start — the start's own record
    wins so the row reflects what is actually running.
    """
    spec = _find_spec(name)
    if spec is None:
        raise ValueError(f"unknown service '{name}'")
    if not spec.restartable:
        raise ValueError(f"service '{name}' is boot-only and cannot be "
                         "restarted at runtime")
    if spec.stop is not None:
        try:
            spec.stop()
            log.info("Service '%s' stopped for restart", name)
        except Exception as exc:
            log.warning("Stop before restart of '%s' failed: %s",
                        name, exc)
    _run(spec)
    return results().get(name, {})
