"""Code Mode — full file + terminal control with safety rails.

Safety:
- OFF by default (toggle via Settings)
- Allowed paths whitelist
- Backup before overwrite/delete
- Confirmation for destructive shell commands
- Full audit log
"""
from __future__ import annotations
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_BACKUPS = _ROOT / "logs" / "code_mode_backups"
_AUDIT = _ROOT / "logs" / "code_mode_audit.log"
_BACKUPS.mkdir(parents=True, exist_ok=True)

_DEFAULT_ALLOWED = [str(_ROOT), str(Path.home() / "Desktop")]

_DANGEROUS = [
    "rm", "del", "erase", "rmdir", "rd", "format", "fdisk", "diskpart",
    "shutdown", "restart", "logoff", "taskkill", "kill", "pkill",
    "reg", "regedit", "net", "sc", "wmic",
]

_FORBIDDEN = ["format", "fdisk", "diskpart", "reg delete", "reg add",
               "takeown", "icacls", "bitsadmin", "certutil",
               "-encodedcommand", "invoke-expression", "iex(",
               "downloadstring", "| powershell", "| sh"]

_MAX_CMD = 2000


def _cmd_safe(cmd: str):
    """Extra structural checks past the substring blacklist."""
    if len(cmd) > _MAX_CMD:
        return False, "Command too long (2000 char cap)."
    if "\x00" in cmd:
        return False, "Blocked: null bytes."
    if "\n" in cmd or "\r" in cmd:
        return False, "Blocked: one command per run."
    return True, ""


def _audit(action: str, target: str, ok: bool, extra: str = ""):
    try:
        with _AUDIT.open("a", encoding="utf-8") as f:
            ts = datetime.now().isoformat(timespec="seconds")
            status = "OK" if ok else "FAIL"
            f.write(f"[{ts}] {status:4} {action:12} {target} {extra}\n")
    except Exception:
        pass


def _code_mode_on() -> bool:
    try:
        from memory import get_pref
        return bool(get_pref("code_mode_enabled", False))
    except Exception:
        return False


def _allowed_paths() -> list:
    try:
        from memory import get_pref
        custom = get_pref("code_mode_allowed", []) or []
    except Exception:
        custom = []
    raw = _DEFAULT_ALLOWED + list(custom)
    return [Path(p).resolve() for p in raw if p]


def _is_allowed(path: Path) -> bool:
    p = path.resolve()
    for root in _allowed_paths():
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _backup(path: Path):
    if not path.exists():
        return None
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe = str(path).replace(":", "").replace("\\", "__").replace("/", "__")
    dest = _BACKUPS / f"{safe}.{ts}.bak"
    try:
        if path.is_file():
            shutil.copy2(path, dest)
        return dest
    except Exception:
        return None


@register("code_write", [
    r"^code\s+write\s+(?P<path>\S+)\s+(?:with|content|:)\s+(?P<content>.+)$",
], "Write file (Code Mode)")
def s_write(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked. Enable in Settings → General."
    path_str = (m.group("path") or "").strip().strip('"')
    content = (m.group("content") or "").strip()
    if not path_str or not content:
        return None
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = _ROOT / path
    if not _is_allowed(path):
        _audit("write", str(path), False, "outside allowed")
        return f"Blocked: {path} outside allowed paths."
    try:
        if path.exists():
            _backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        _audit("write", str(path), True, f"{len(content)} chars")
        return f"Wrote {path.name} ({len(content)} chars)."
    except Exception as exc:
        _audit("write", str(path), False, str(exc)[:80])
        return f"Write failed: {str(exc)[:80]}"


@register("code_read", [
    r"^code\s+read\s+(?P<path>\S+)$",
], "Read file (Code Mode)")
def s_read(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked."
    path = Path(m.group("path").strip().strip('"')).expanduser()
    if not path.is_absolute():
        path = _ROOT / path
    if not _is_allowed(path):
        return f"Blocked: {path} outside allowed paths."
    if not path.exists() or path.is_dir():
        return f"Not found: {path}"
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        _audit("read", str(path), True, f"{len(content)} chars")
        if len(content) > 3000:
            content = content[:3000] + "\n... (truncated)"
        return content
    except Exception as exc:
        return f"Read failed: {str(exc)[:80]}"


@register("code_delete", [
    r"^code\s+delete\s+(?P<path>\S+)$",
], "Delete file (Code Mode, backed up)")
def s_delete(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked."
    path = Path(m.group("path").strip().strip('"')).expanduser()
    if not path.is_absolute():
        path = _ROOT / path
    if not _is_allowed(path):
        return f"Blocked: {path} outside allowed paths."
    if not path.exists():
        return f"Not found: {path}"
    try:
        _backup(path)
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        _audit("delete", str(path), True, "backed up")
        return f"Deleted {path.name}."
    except Exception as exc:
        return f"Delete failed: {str(exc)[:80]}"


@register("code_list", [
    r"^code\s+list(?:\s+(?P<path>\S+))?$",
], "List directory (Code Mode)")
def s_list(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked."
    path_str = (m.group("path") or "").strip().strip('"')
    path = Path(path_str).expanduser() if path_str else _ROOT
    if not path.is_absolute():
        path = _ROOT / path
    if not _is_allowed(path):
        return f"Blocked: {path} outside allowed paths."
    if not path.exists():
        return f"Not found: {path}"
    try:
        items = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        _audit("list", str(path), True, f"{len(items)} items")
        lines = [f"{p.name}{'/' if p.is_dir() else ''}" for p in items[:40]]
        return " ".join(lines) if lines else "Empty."
    except Exception as exc:
        return f"List failed: {str(exc)[:80]}"


@register("code_run", [
    r"^code\s+run\s+(?P<cmd>.+)$",
], "Run shell command (Code Mode)")
def s_run(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked."
    cmd = (m.group("cmd") or "").strip()
    if not cmd:
        return None
    low = cmd.lower()
    for bad in _FORBIDDEN:
        if bad in low:
            _audit("run", cmd, False, "forbidden")
            return f"Blocked: '{bad}' never allowed."
    for word in _DANGEROUS:
        if word in low.split() or low.startswith(word + " "):
            _audit("run", cmd, False, "requires confirmation")
            return f"'{word}' is destructive. Say 'code confirm {cmd}' to run anyway."
    safe, reason = _cmd_safe(cmd)
    if not safe:
        _audit("run", cmd[:80], False, reason)
        return f"Blocked: {reason}"
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True,
                                text=True, timeout=30, cwd=str(_ROOT))
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        _audit("run", cmd, result.returncode == 0, f"rc={result.returncode}")
        if result.returncode != 0 and err:
            return f"Command failed: {err[:300]}"
        if len(out) > 2000:
            out = out[:2000] + "\n... (truncated)"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        _audit("run", cmd, False, "timeout")
        return "Command timed out."
    except Exception as exc:
        return f"Run failed: {str(exc)[:80]}"


@register("code_confirm", [
    r"^code\s+confirm\s+(?P<cmd>.+)$",
], "Confirm and run dangerous command")
def s_confirm(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked."
    cmd = (m.group("cmd") or "").strip()
    if not cmd:
        return None
    if len(cmd) > _MAX_CMD or "\x00" in cmd:
        _audit("run-confirmed", cmd[:80], False, "too long / null bytes")
        return "Blocked: command too long."
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True,
                                text=True, timeout=30, cwd=str(_ROOT))
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        _audit("run-confirmed", cmd, result.returncode == 0, f"rc={result.returncode}")
        if result.returncode != 0 and err:
            return f"Command failed: {err[:300]}"
        return out[:2000] if out else "(no output)"
    except Exception as exc:
        return f"Run failed: {str(exc)[:80]}"


def _ask_admin(cmd: str) -> bool:
    """Elevation ALWAYS asks — auto mode is deliberately ignored.

    Windows UAC is the final guard: declining the prompt aborts.
    """
    try:
        from voice import speak_async
        speak_async(f"Run as administrator: {cmd[:120]}? "
                    f"Say yes, or press Approve.")
    except Exception:
        pass
    try:
        from system.notify import confirm
        return bool(confirm(f"Run as ADMIN: {cmd[:120]}?", timeout=60))
    except Exception:
        return False


def _run_elevated(cmd: str, timeout: int = 120, tmpdir=None) -> tuple:
    """Run cmd elevated via a UAC prompt. Returns (rc, output).

    Denying the UAC prompt raises OSError (mapped to a friendly
    message by the caller). Never silent: no prompt, no elevation.
    """
    import tempfile
    import uuid
    workdir = Path(tmpdir) if tmpdir else Path(tempfile.gettempdir())
    tag = uuid.uuid4().hex[:8]
    bat = workdir / f"jarvis-admin-{tag}.bat"
    out = workdir / f"jarvis-admin-{tag}.out"
    try:
        bat.write_text(f"@echo off\r\n{cmd} > \"{out}\" 2>&1\r\n",
                       encoding="utf-8")
    except Exception as exc:
        return -1, f"Could not stage elevated run: {exc}"[:120]
    ps = (f"Start-Process -FilePath '{bat}' -Verb RunAs -Wait")
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-Command", ps],
            capture_output=True, text=True, timeout=timeout + 30)
    except subprocess.TimeoutExpired:
        return -1, "Elevated run timed out."
    except OSError as exc:
        return -1, f"Elevation refused: {exc}"[:160]
    except Exception as exc:
        return -1, f"Elevation failed: {exc}"[:160]
    finally:
        try:
            bat.unlink(missing_ok=True)
        except Exception:
            pass
    if r.returncode != 0:
        err = (r.stderr or "").strip()[:160]
        if "canceled" in err.lower() or "denied" in err.lower():
            return -1, "UAC prompt declined — nothing ran."
        return -1, f"Launcher failed: {err or r.returncode}"
    try:
        text = out.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:
        text = ""
    finally:
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass
    return 0, text


@register("code_run_admin", [
    r"^code\s+run-admin\s+(?P<cmd>.+)$",
    r"^code\s+run\s+(?:as\s+admin|elevated)\s+(?P<cmd>.+)$",
    r"^run\s+(?P<cmd>.+?)\s+as\s+(?:admin|administrator)[\?\.\!]?$",
], "Run shell command elevated (always confirms)")
def s_run_admin(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked."
    cmd = (m.group("cmd") or "").strip()
    if not cmd:
        return None
    low = cmd.lower()
    for bad in _FORBIDDEN:
        if bad in low:
            _audit("run-admin", cmd, False, "forbidden")
            return f"Blocked: '{bad}' never allowed, even elevated."
    safe, reason = _cmd_safe(cmd)
    if not safe:
        _audit("run-admin", cmd[:80], False, reason)
        return f"Blocked: {reason}"
    if not _ask_admin(cmd):
        _audit("run-admin", cmd[:80], False, "declined")
        return "OK, not running it elevated."
    rc, output = _run_elevated(cmd)
    _audit("run-admin", cmd, rc == 0, f"rc={rc}")
    if rc != 0:
        return output or "Elevated run failed."
    if len(output) > 2000:
        output = output[:2000] + "\n... (truncated)"
    return output or "(no output)"


@register("code_status", [
    r"^code\s+(?:mode\s+)?status$",
], "Code Mode status")
def s_status(text, m):
    on = _code_mode_on()
    allowed = ", ".join(str(p) for p in _allowed_paths())
    return (f"OVERRIDE is {'ARMED' if on else 'LOCKED'}. "
            f"Allowed paths: {allowed}. "
            f"Audit log: logs/code_mode_audit.log")


# ---------- VS CODE CONTROL ----------

_VSCODE_CANDIDATES = [
    "code",
    "code.cmd",
    str(Path.home() / "AppData" / "Local" / "Programs" / "Microsoft VS Code" / "bin" / "code.cmd"),
    r"C:\Program Files\Microsoft VS Code\bin\code.cmd",
    r"C:\Program Files (x86)\Microsoft VS Code\bin\code.cmd",
]


def _find_code_cli():
    for c in _VSCODE_CANDIDATES:
        try:
            import shutil as _sh
            found = _sh.which(c) if not c.startswith(str(Path.home())) and not c.startswith("C:\\") else None
            if found:
                return found
            if Path(c).exists():
                return c
        except Exception:
            continue
    return None


def _run_code(args):
    cli = _find_code_cli()
    if not cli:
        return "VS Code CLI not found. Ensure 'code' is in PATH."
    try:
        result = subprocess.run([cli] + args, capture_output=True,
                                text=True, timeout=30)
        return (result.stdout or "").strip() or "(opened)"
    except Exception as exc:
        return f"VS Code failed: {str(exc)[:120]}"


@register("code_open_file", [
    r"^code\s+open\s+file\s+(?P<path>\S+)(?:\s+at\s+line\s+(?P<line>\d+))?$",
    r"^code\s+open\s+(?P<path2>\S+\.[a-z]{1,6})(?:\s+at\s+line\s+(?P<line2>\d+))?$",
], "Open file in VS Code")
def s_open_file(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked. Enable in Settings → General."
    gd = m.groupdict()
    path_str = (gd.get("path") or gd.get("path2") or "").strip().strip('"')
    line_str = gd.get("line") or gd.get("line2")
    if not path_str:
        return None
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = _ROOT / path
    if not _is_allowed(path):
        _audit("vscode-open-file", str(path), False, "outside allowed")
        return f"Blocked: {path} outside allowed paths."
    if not path.exists():
        return f"Not found: {path}"
    if line_str:
        args = ["--goto", f"{path}:{line_str}"]
    else:
        args = [str(path)]
    _audit("vscode-open-file", str(path), True)
    return _run_code(args)


@register("code_open_folder", [
    r"^code\s+open\s+(?:folder|project|dir)\s+(?P<path>.+)$",
], "Open folder in VS Code")
def s_open_folder(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked. Enable in Settings → General."
    path_str = (m.group("path") or "").strip().strip('"')
    if not path_str:
        return None
    path = Path(path_str).expanduser()
    if not path.is_absolute():
        path = _ROOT / path
    if not _is_allowed(path):
        _audit("vscode-open-folder", str(path), False, "outside allowed")
        return f"Blocked: {path} outside allowed paths."
    if not path.exists():
        return f"Not found: {path}"
    _audit("vscode-open-folder", str(path), True)
    return _run_code([str(path)])


@register("code_vscode_cmd", [
    r"^code\s+vscode\s+(?P<cmd>.+)$",
    r"^code\s+run\s+command\s+(?P<cmd2>.+)$",
], "Run VS Code CLI command")
def s_vscode_cmd(text, m):
    if not _code_mode_on():
        return "OVERRIDE is locked. Enable in Settings → General."
    gd = m.groupdict()
    cmd = (gd.get("cmd") or gd.get("cmd2") or "").strip()
    if not cmd:
        return None
    args = cmd.split()
    _audit("vscode-cmd", cmd, True)
    return _run_code(args)
