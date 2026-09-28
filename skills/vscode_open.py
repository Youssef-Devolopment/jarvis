"""Open files and folders in VS Code via CLI."""
from __future__ import annotations
import subprocess
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _open_in_code(target: str, line: int = 0) -> str:
    try:
        p = Path(target).expanduser()
        if not p.exists():
            return f"Not found: {target}"
        cmd = ["code"]
        if line > 0:
            cmd.append("--goto")
            cmd.append(f"{p}:{line}")
        else:
            cmd.append(str(p))
        subprocess.Popen(cmd, shell=True)
        kind = "folder" if p.is_dir() else "file"
        return f"Opened {kind} {p.name} in VS Code."
    except Exception as exc:
        return f"VS Code open failed: {str(exc)[:80]}"


@register("vscode_open", [
    r"^(?:open|edit)\s+(?:in\s+)?vs\s*code\s+(?P<path>.+?)[\?\.\!]?$",
    r"^(?:open|edit)\s+(?P<path2>.+?)\s+in\s+vs\s*code[\?\.\!]?$",
], "Open in VS Code")
def s_vscode(text, m):
    gd = m.groupdict()
    target = (gd.get("path") or gd.get("path2") or "").strip().strip('"').strip("'")
    if not target:
        return None
    return _open_in_code(target)


@register("vscode_open_line", [
    r"^open\s+(?P<path>.+?)\s+at\s+line\s+(?P<line>\d+)[\?\.\!]?$",
], "Open file at line")
def s_vscode_line(text, m):
    path = m.group("path").strip().strip('"').strip("'")
    try:
        line = int(m.group("line"))
    except Exception:
        line = 0
    return _open_in_code(path, line)
