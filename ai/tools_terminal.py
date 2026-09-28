"""Terminal tools for JARVIS — safe shell command execution."""
from __future__ import annotations
import subprocess
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent

_BANNED = {
    "rm", "del", "erase", "rmdir", "rd", "format", "fdisk", "diskpart",
    "shutdown", "restart", "logoff", "taskkill", "kill", "pkill",
    "reg", "regedit", "net", "sc", "wmic", "takeown", "icacls",
}

_RISKY = {"install", "uninstall", "update", "upgrade", "reset", "clean", "purge", "force"}

_EXTRA_BANNED = {"encodedcommand", "invoke-expression", "downloadstring",
                 "bitsadmin", "certutil"}
_DASH_TOKENS = {"enc", "encodedcommand", "iex", "invoke-expression"}


def _check_command(cmd: str):
    if len(cmd) > 2000:
        return False, "command too long (2000 char cap)."
    if "\x00" in cmd:
        return False, "null bytes blocked."
    first_word = cmd.strip().split()[0].lower() if cmd.strip() else ""
    base = Path(first_word).name.lower()
    if base in _BANNED:
        return False, f"'{base}' is banned for safety."
    for bad in _BANNED | _EXTRA_BANNED:
        if f" {bad} " in f" {cmd.lower()} " or cmd.lower().startswith(bad + " "):
            return False, f"'{bad}' is banned for safety."
    for tok in cmd.lower().replace(",", " ").replace(";", " ").split():
        if tok.lstrip("-").lstrip("/") in _DASH_TOKENS:
            return False, f"'{tok}' is banned for safety."
    return True, ""


def term_run(command: str, timeout: int = 30) -> str:
    if not command or not command.strip():
        return "[error] empty command"
    allowed, reason = _check_command(command)
    if not allowed:
        return f"[blocked] {reason}"
    low = command.lower()
    for risk in _RISKY:
        if risk in low:
            log.warning("Risky command: %s", command[:80])
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=str(_ROOT), encoding="utf-8",
            errors="replace")
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        rc = result.returncode
        parts = []
        if out:
            parts.append(out[:3000])
        if err:
            parts.append(f"[stderr]\n{err[:1000]}")
        if rc != 0:
            parts.append(f"[exit code {rc}]")
        return "\n".join(parts) if parts else "[no output]"
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"
    except Exception as exc:
        return f"[error] {exc}"


def term_python(code: str, timeout: int = 30) -> str:
    if not code or not code.strip():
        return "[error] empty code"
    try:
        result = subprocess.run(
            ["python", "-c", code], capture_output=True, text=True,
            timeout=timeout, cwd=str(_ROOT), encoding="utf-8",
            errors="replace")
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()
        parts = []
        if out:
            parts.append(out[:2000])
        if err:
            parts.append(f"[stderr]\n{err[:800]}")
        return "\n".join(parts) if parts else "[no output]"
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"
    except Exception as exc:
        return f"[error] {exc}"
