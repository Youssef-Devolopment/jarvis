"""Auto-start JARVIS on Windows login via Startup shortcut."""
from __future__ import annotations
import os
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_PROJECT = Path(__file__).resolve().parent.parent
_LNK_NAME = "JARVIS.lnk"


def _startup_dir() -> Path:
    appdata = os.getenv("APPDATA") or ""
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _lnk_path() -> Path:
    return _startup_dir() / _LNK_NAME


def is_enabled() -> bool:
    return _lnk_path().exists()


def enable() -> bool:
    """Enable login autostart: silent desktop mode + fresh browser window.

    Points the Startup shortcut at pythonw.exe desktop.py --open so
    Windows login starts the server (tray + hotkey, no console) and
    opens JARVIS in a new browser window.
    """
    try:
        import sys
        d = _startup_dir()
        d.mkdir(parents=True, exist_ok=True)
        venv_pythonw = _PROJECT / ".venv" / "Scripts" / "pythonw.exe"
        if venv_pythonw.exists():
            target = str(venv_pythonw)
        else:
            target = sys.executable
        args = "desktop.py --open"
        import pythoncom
        from win32com.client import Dispatch
        pythoncom.CoInitialize()
        shell = Dispatch("WScript.Shell")
        sc = shell.CreateShortCut(str(_lnk_path()))
        sc.TargetPath = target
        sc.Arguments = args
        sc.WorkingDirectory = str(_PROJECT)
        sc.WindowStyle = 7
        sc.Description = "JARVIS voice assistant"
        sc.save()
        log.info("Auto-start enabled -> %s (%s %s)", _lnk_path(), target, args)
        return True
    except Exception as exc:
        log.exception("Auto-start enable failed: %s", exc)
        return False


def disable() -> bool:
    try:
        p = _lnk_path()
        if p.exists():
            p.unlink()
            log.info("Auto-start disabled")
        return True
    except Exception as exc:
        log.exception("Auto-start disable failed: %s", exc)
        return False
