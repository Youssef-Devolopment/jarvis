"""Filesystem tools for JARVIS."""
from __future__ import annotations
import fnmatch
import shutil
import time
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_BACKUPS = _ROOT / "logs" / "tool_backups"
_BACKUPS.mkdir(parents=True, exist_ok=True)

_ALLOWED_ROOTS = [
    _ROOT,
    Path.home() / "Desktop",
    Path.home() / "Documents",
    Path.home() / "Downloads",
]

_MAX_READ_BYTES = 100_000
_MAX_RESULTS = 50


def _safe_path(p: str):
    try:
        path = Path(p).expanduser().resolve()
    except Exception:
        return None
    for root in _ALLOWED_ROOTS:
        try:
            path.relative_to(root.resolve())
            return path
        except ValueError:
            continue
    return None


def _backup(path: Path):
    if not path.exists() or path.is_dir():
        return None
    ts = time.strftime("%Y%m%d_%H%M%S")
    safe = str(path).replace(":", "").replace("\\", "__").replace("/", "__")
    dest = _BACKUPS / f"{safe}.{ts}.bak"
    try:
        shutil.copy2(path, dest)
        return dest
    except Exception:
        return None


def fs_read(path: str, max_bytes: int = _MAX_READ_BYTES) -> str:
    p = _safe_path(path)
    if not p:
        return f"[blocked] {path} outside allowed paths."
    if not p.exists():
        return f"[not found] {path}"
    if p.is_dir():
        return f"[is a directory] {path}"
    try:
        data = p.read_bytes()[:max_bytes]
        text = data.decode("utf-8", errors="replace")
        if len(data) == max_bytes:
            text += f"\n[... truncated at {max_bytes} bytes]"
        return text
    except Exception as exc:
        return f"[error] {exc}"


def fs_write(path: str, content: str) -> str:
    p = _safe_path(path)
    if not p:
        return f"[blocked] {path} outside allowed paths."
    try:
        if p.exists():
            _backup(p)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"[ok] wrote {len(content)} chars to {p.name}"
    except Exception as exc:
        return f"[error] {exc}"


def fs_append(path: str, content: str) -> str:
    p = _safe_path(path)
    if not p:
        return f"[blocked] {path} outside allowed paths."
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"[ok] appended {len(content)} chars to {p.name}"
    except Exception as exc:
        return f"[error] {exc}"


def fs_list(path: str = ".") -> str:
    p = _safe_path(path)
    if not p:
        return f"[blocked] {path} outside allowed paths."
    if not p.exists():
        return f"[not found] {path}"
    if not p.is_dir():
        return f"[not a directory] {path}"
    try:
        items = sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        lines = []
        for item in items[:100]:
            if item.is_dir():
                lines.append(f"DIR   {item.name}/")
            else:
                size = item.stat().st_size
                lines.append(f"FILE  {item.name}  ({size} bytes)")
        return "\n".join(lines) if lines else "[empty]"
    except Exception as exc:
        return f"[error] {exc}"


def fs_search(pattern: str, root: str = ".", max_hits: int = _MAX_RESULTS) -> str:
    p = _safe_path(root)
    if not p:
        return f"[blocked] {root} outside allowed paths."
    if not p.exists():
        return f"[not found] {root}"
    try:
        hits = []
        for f in p.rglob("*"):
            if len(hits) >= max_hits:
                break
            if f.is_file() and fnmatch.fnmatch(f.name.lower(), f"*{pattern.lower()}*"):
                hits.append(str(f.relative_to(p)))
        if not hits:
            return f"[no matches for '{pattern}']"
        return f"Found {len(hits)} matches:\n" + "\n".join(hits)
    except Exception as exc:
        return f"[error] {exc}"


def fs_delete(path: str) -> str:
    p = _safe_path(path)
    if not p:
        return f"[blocked] {path} outside allowed paths."
    if not p.exists():
        return f"[not found] {path}"
    try:
        _backup(p)
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
        return f"[ok] deleted {p.name} (backup saved)"
    except Exception as exc:
        return f"[error] {exc}"


def fs_mkdir(path: str) -> str:
    p = _safe_path(path)
    if not p:
        return f"[blocked] {path} outside allowed paths."
    try:
        p.mkdir(parents=True, exist_ok=True)
        return f"[ok] created {p}"
    except Exception as exc:
        return f"[error] {exc}"
