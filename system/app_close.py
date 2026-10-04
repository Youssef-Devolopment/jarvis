"""Close ANY desktop app by name. Companion to system/launch.py (open).

Resolution reuses the same layers: learned store -> ALIASES ->
running processes. Safety mirrors ai/ports.kill_listener: refuse
Windows-critical processes and JARVIS's own interpreters, and ask
before closing anything that wasn't explicitly learned or aliased.

Closing is graceful first (terminate: apps may prompt to save and
stay alive — reported, not forced), SIGKILL-style only for
leftovers, then verified gone.
"""
from __future__ import annotations
import os
from logger import get_logger

log = get_logger(__name__)

# Never close these, no matter who asks.
NEVER_KILL = {
    "system", "registry", "smss.exe", "csrss.exe", "wininit.exe",
    "services.exe", "lsass.exe", "lsm.exe", "winlogon.exe",
    "svchost.exe", "dwm.exe", "explorer.exe", "taskhostw.exe",
    "sihost.exe", "ctfmon.exe", "conhost.exe", "fontdrvhost.exe",
    "userinit.exe", "runtimebroker.exe", "searchhost.exe",
    "startmenuexperiencehost.exe", "textinputhost.exe",
}

# Markers that identify JARVIS's own interpreter in a cmdline.
_SELF_MARKERS = ("desktop.py", "run.py", "server.py", "check.py",
                 "jarvis", ".venv")

# Alias values that are CLI shims, not the real process image.
_SHIM_IMAGES = {
    "code": ["Code.exe"],
    "wt.exe": ["WindowsTerminal.exe", "wt.exe"],
}


def _learned_map() -> dict:
    """display-norm -> exe basename from the learner store."""
    try:
        from system import app_learner
        out = {}
        for entry in app_learner.learned_list():
            name = str(entry.get("name") or "").strip().lower()
            path = str(entry.get("path") or "")
            if name and path:
                from pathlib import Path
                out[name] = Path(path).name
        return out
    except Exception:
        return {}


def _candidate_exes(name: str) -> tuple[list[str], bool]:
    """Map a spoken app name to likely exe names + instant flag.

    instant=True for explicitly learned apps and curated aliases
    (mirrors launch SAFE_INSTANT: the user already vetted these).
    """
    key = (name or "").strip().lower()
    if not key:
        return [], False
    learned = _learned_map()
    if key in learned:
        return [learned[key]], True
    try:
        from system.launch import ALIASES
    except Exception:
        ALIASES = {}
    if key in ALIASES:
        val = ALIASES[key]
        if val in _SHIM_IMAGES:
            return list(_SHIM_IMAGES[val]), True
        if val.endswith(".exe"):
            return [val], True
        if val.startswith("ms-"):
            return [], False  # store/settings pages: nothing to kill
        return [val + ".exe"], True
    if key.endswith(".exe"):
        return [key], False
    return [key + ".exe"], False


def _is_self(proc) -> bool:
    """True if this process looks like JARVIS itself."""
    try:
        if proc.pid in (os.getpid(), 0, 1, 4):
            return True
        cmd = " ".join(proc.cmdline() or []).lower()
        exe = str(proc.exe() if hasattr(proc, "exe") else "") or ""
        if ".venv" in exe.replace("\\", "/").lower():
            return True
        return any(m in cmd for m in _SELF_MARKERS)
    except Exception:
        return False


def _iter_procs():
    try:
        import psutil
        return list(psutil.process_iter())
    except Exception as exc:
        log.warning("Process list unavailable: %s", exc)
        return []


def _proc_name(proc) -> str:
    try:
        n = proc.name() or ""
        return n.lower()
    except Exception:
        return ""


def resolve_close(name: str) -> dict:
    """Pure lookup: which running processes would 'close <name>' hit?"""
    key = (name or "").strip().lower()
    if not key:
        return {"status": "unknown", "exe": "", "pids": []}
    exes, instant = _candidate_exes(key)
    if not exes:
        return {"status": "refused", "exe": "", "pids": [],
                "error": f"Nothing to close for '{name}'."}
    wanted = set(exes)
    procs = _iter_procs()
    running = [p for p in procs if _proc_name(p) in wanted]
    exe = exes[0]
    if exe in NEVER_KILL:
        return {"status": "refused", "exe": exe, "pids": [],
                "error": f"I won't close {exe} — it's a system process."}
    if not running:
        return {"status": "not_running", "exe": exe, "pids": []}
    if all(_is_self(p) for p in running):
        return {"status": "refused", "exe": exe,
                "pids": [p.pid for p in running],
                "error": f"I won't close {exe} — that's me."}
    return {"status": "found", "exe": exe, "instant": instant,
            "pids": [p.pid for p in running
                     if not _is_self(p) and _proc_name(p) not in NEVER_KILL]}


def _close_pids(pids: list[int]) -> tuple[int, int]:
    """Graceful terminate first, force leftovers. Returns (closed, alive)."""
    import psutil
    import time
    targets = []
    for pid in pids:
        try:
            targets.append(psutil.Process(pid))
        except Exception:
            continue
    for p in targets:
        try:
            p.terminate()
        except Exception:
            pass
    deadline = time.time() + 5
    while time.time() < deadline:
        if not any(_alive(p) for p in targets):
            break
        time.sleep(0.3)
    for p in targets:
        if _alive(p):
            try:
                p.kill()
            except Exception:
                pass
    try:
        for p in targets:
            try:
                p.wait(timeout=3)
            except Exception:
                pass
    except Exception:
        pass
    alive = sum(1 for p in targets if _alive(p))
    return len(targets) - alive, alive


def _alive(proc) -> bool:
    try:
        return proc.is_running()
    except Exception:
        return False


def close_by_name(name: str, ask_fn=None) -> dict:
    """Close an app by spoken name. ask_fn(display)->bool for confirm.

    Returns {"ok", "output", ...}. Never raises for expected cases.
    """
    display = (name or "").strip()
    r = resolve_close(display)
    status = r["status"]
    if status == "unknown":
        return {"ok": False,
                "output": f"Close what? I didn't catch an app name."}
    if status == "refused":
        return {"ok": False, "output": r["error"]}
    if status == "not_running":
        return {"ok": False,
                "output": f"{r['exe']} isn't running."}
    if not r["pids"]:
        return {"ok": False,
                "output": f"Nothing I can safely close for '{display}'."}
    if not r.get("instant"):
        ok = False
        try:
            from system.app_learner import auto_mode
            if auto_mode():
                ok = True  # standing yes; refusals already handled above
        except Exception:
            pass
        if not ok and ask_fn is not None:
            try:
                ok = bool(ask_fn(display))
            except Exception:
                ok = False
        if not ok:
            return {"ok": False, "declined": True,
                    "output": "OK, not closing it."}
    closed, alive = _close_pids(r["pids"])
    n = len(r["pids"])
    plural = "es" if n != 1 else ""
    if alive:
        out = (f"Asked {r['exe']} to close ({closed}/{n} gone). "
               f"{alive} still running — check save dialogs, sir.")
        outcome = closed > 0
    else:
        out = f"Closed {display} ({n} process{plural})."
        outcome = True
    try:
        from memory import context as ctx
        ctx.log_event("app", f"closed {display} ({closed}/{n})")
    except Exception:
        pass
    try:
        from skills.code_mode import _audit
        _audit("close", r["exe"], outcome, display)
    except Exception:
        pass
    return {"ok": outcome, "output": out, "killed": closed,
            "alive": alive, "exe": r["exe"]}
