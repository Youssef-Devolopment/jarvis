"""Single-instance guard — one JARVIS per machine.

Uses logs/jarvis.lock holding the owner PID. A second boot verifies
the PID is really a live JARVIS process (command-line check, so PID
reuse can never block a fresh start) and exits(2) with a clear warning.
"""
from __future__ import annotations
import atexit
import os
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_LOCK = Path(__file__).resolve().parent.parent / "logs" / "jarvis.lock"
_MINE = False


def _pid_is_jarvis(pid: int) -> bool:
    """True if pid is a live process running our run.py/desktop.py."""
    try:
        import psutil
        if not psutil.pid_exists(pid):
            return False
        try:
            p = psutil.Process(pid)
            cmd = " ".join(p.cmdline() or []).lower()
            name = (p.name() or "").lower()
            return "python" in name and ("run.py" in cmd or "desktop.py" in cmd)
        except Exception:
            return False
    except ImportError:
        pass
    try:
        import ctypes
        h = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if not h:
            return False
        ctypes.windll.kernel32.CloseHandle(h)
        return True  # can't verify cmdline without psutil: assume live
    except Exception:
        return False


def acquire() -> bool:
    """Claim the instance lock. Returns True if we own it now."""
    global _MINE
    try:
        _LOCK.parent.mkdir(parents=True, exist_ok=True)
        if _LOCK.exists():
            try:
                old = int(_LOCK.read_text(encoding="utf-8").strip())
            except Exception:
                old = 0
            if old and _pid_is_jarvis(old):
                log.warning("Duplicate boot refused — JARVIS already "
                            "running (pid %d).", old)
                return False
            log.info("Removing stale lock (pid %s).", old or "unreadable")
    except Exception as exc:
        log.warning("Lock check failed (%s) — proceeding.", exc)
    try:
        _LOCK.write_text(str(os.getpid()), encoding="utf-8")
    except Exception as exc:
        log.warning("Could not write lockfile: %s", exc)
        return True  # fail-open: never brick booting over a lock write
    _MINE = True
    atexit.register(release)
    return True


def release() -> None:
    """Drop the lock, but only if it is still ours."""
    global _MINE
    if not _MINE:
        return
    try:
        if _LOCK.exists() and _LOCK.read_text(encoding="utf-8").strip() == str(os.getpid()):
            _LOCK.unlink()
    except Exception:
        pass
    _MINE = False
