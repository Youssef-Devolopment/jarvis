"""Auto-start JARVIS on Windows login — three independent mechanisms.

Power-button flow: PC on → Windows login → JARVIS runs automatically.

  1. Startup-folder shortcut  (JARVIS.lnk → pythonw desktop.py --open)
     — classic, user-visible, toggleable in Task Manager.
  2. HKCU ...\\CurrentVersion\\Run registry key
     — no admin needed, survives Startup-folder cleanup.
  3. Task Scheduler logon task (JARVIS, +15s delay)
     — needs elevation once; survives "disable startup apps".

All start the same desktop mode (Flask + tray + hotkeys + overlay);
the single-instance guard makes a double-fire harmless (second one
logs a warning and exits).
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_PROJECT = Path(__file__).resolve().parent.parent
_LNK_NAME = "JARVIS.lnk"
_TASK_NAME = "JARVIS"


# ---------- paths ---------------------------------------------------------
def _startup_dir() -> Path:
    appdata = os.getenv("APPDATA") or ""
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _lnk_path() -> Path:
    return _startup_dir() / _LNK_NAME


def _pythonw() -> Path:
    venv = _PROJECT / ".venv" / "Scripts" / "pythonw.exe"
    if venv.exists():
        return venv
    import sys
    return Path(sys.executable)


# ---------- scheduled task ------------------------------------------------
def _task_exists() -> bool:
    try:
        r = subprocess.run(["schtasks", "/query", "/tn", _TASK_NAME],
                           capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _task_xml() -> str:
    """Task XML with a real working directory.

    The legacy `schtasks /create /tr ...` form starts the process in
    %WINDIR%\\System32, so .env/logs resolve to the wrong place and
    the app boots keyless. The XML form sets WorkingDirectory to the
    project root. InteractiveToken = runs as the creating user.
    """
    from xml.sax.saxutils import escape
    cmd = escape(str(_pythonw()))
    workdir = escape(str(_PROJECT))
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>JARVIS autostart (login +15s)</Description>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
      <Delay>PT15S</Delay>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{cmd}</Command>
      <Arguments>desktop.py --open</Arguments>
      <WorkingDirectory>{workdir}</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
"""


def _task_create() -> bool:
    """Logon task, delayed 15s so the desktop can settle first."""
    import tempfile
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".xml",
                                         delete=False,
                                         encoding="utf-16") as f:
            f.write(_task_xml())
            tmp = f.name
        r = subprocess.run(
            ["schtasks", "/create", "/tn", _TASK_NAME,
             "/xml", tmp, "/f"],
            capture_output=True, timeout=20, text=True)
        if r.returncode == 0:
            log.info("Logon task created: %s (delay 15s, workdir set)",
                     _TASK_NAME)
            return True
        log.warning("schtasks xml create failed: %s",
                    (r.stderr or r.stdout or "").strip()[:200])
    except Exception as exc:
        log.warning("schtasks xml create error: %s", exc)
    finally:
        try:
            if tmp:
                Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass
    return _task_create_legacy()


def _task_create_legacy() -> bool:
    """Old schtasks form (no working directory). Fallback only."""
    cmd = f'"{_pythonw()}" desktop.py --open'
    try:
        r = subprocess.run(
            ["schtasks", "/create", "/tn", _TASK_NAME, "/tr", cmd,
             "/sc", "onlogon", "/delay", "0000:15", "/f"],
            capture_output=True, timeout=20, text=True)
        if r.returncode != 0:
            log.warning("schtasks create failed: %s",
                        (r.stderr or r.stdout or "").strip()[:200])
            return False
        log.info("Logon task created (legacy): %s", _TASK_NAME)
        return True
    except Exception as exc:
        log.warning("schtasks create error: %s", exc)
        return False


def _task_remove() -> bool:
    try:
        r = subprocess.run(["schtasks", "/delete", "/tn", _TASK_NAME, "/f"],
                           capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


# ---------- registry Run key (no admin needed) ---------------------------
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "JARVIS"


def _reg_command() -> str:
    return f'"{_pythonw()}" desktop.py --open'


def _reg_exists() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY) as k:
            winreg.QueryValueEx(k, _RUN_NAME)
        return True
    except Exception:
        return False


def _reg_create() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, _RUN_NAME, 0, winreg.REG_SZ,
                              _reg_command())
        log.info("HKCU Run key set: %s", _reg_command())
        return True
    except Exception as exc:
        log.warning("HKCU Run key failed: %s", exc)
        return False


def _reg_remove() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as k:
            winreg.DeleteValue(k, _RUN_NAME)
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False


# ---------- public API ----------------------------------------------------
def is_enabled() -> bool:
    """True when at least one autostart mechanism is armed."""
    return (_lnk_path().exists() or _task_exists()
            or _reg_exists())


def status() -> dict:
    lnk = _lnk_path().exists()
    task = _task_exists()
    reg = _reg_exists()
    return {
        "enabled": lnk or task or reg,
        "shortcut": lnk,
        "scheduled_task": task,
        "run_key": reg,
        "target": f"{_pythonw()} desktop.py --open",
        "trigger": "power button → boot → Windows login → JARVIS (+15s)",
        "mechanisms": sum((lnk, task, reg)),
    }


def enable() -> bool:
    """Arm as many mechanisms as permissions allow (aim: all three)."""
    ok_lnk = False
    try:
        d = _startup_dir()
        d.mkdir(parents=True, exist_ok=True)
        target = str(_pythonw())
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
        ok_lnk = True
        log.info("Auto-start shortcut -> %s (%s %s)", _lnk_path(), target, args)
    except Exception as exc:
        log.exception("Auto-start shortcut failed: %s", exc)

    ok_reg = _reg_create()
    ok_task = _task_create()          # may need elevation; optional
    return ok_lnk or ok_reg or ok_task


def disable() -> bool:
    ok = True
    try:
        p = _lnk_path()
        if p.exists():
            p.unlink()
            log.info("Auto-start shortcut removed")
    except Exception as exc:
        log.exception("Auto-start disable failed: %s", exc)
        ok = False
    if _task_exists():
        ok = _task_remove() and ok
    if _reg_exists():
        ok = _reg_remove() and ok
    if ok:
        log.info("All autostart mechanisms removed")
    return ok
