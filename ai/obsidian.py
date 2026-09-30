"""Obsidian vault backend for JARVIS notes.

Notes live as Markdown files in <vault>/JARVIS/ so they are readable
and editable directly in Obsidian. When no vault is configured or
found, callers fall back to the SQLite notes table.
"""

from __future__ import annotations
import os
import re
from datetime import datetime
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_SUBDIR = "JARVIS"


def _configured_path() -> Path | None:
    raw = (os.getenv("OBSIDIAN_VAULT") or "").strip().strip('"')
    if not raw:
        try:
            from config import get_settings
            raw = (get_settings().obsidian_vault or "").strip()
        except Exception:
            raw = ""
    if raw:
        p = Path(raw).expanduser()
        if p.is_dir():
            return p
        log.warning("OBSIDIAN_VAULT set but not a directory: %s", raw)
    return None


def find_vault() -> Path | None:
    """Return the vault dir, or None when Obsidian isn't set up."""
    cfg = _configured_path()
    if cfg:
        return cfg
    home = Path.home()
    candidates = [
        home / "Documents",
        home / "OneDrive" / "Documents",
        home / "iCloudDrive",
    ]
    seen = []
    for base in candidates:
        if not base.is_dir():
            continue
        try:
            for child in base.iterdir():
                if child.is_dir() and (child / ".obsidian").is_dir():
                    seen.append(child)
        except Exception:
            continue
    if len(seen) == 1:
        return seen[0]
    if seen:
        log.info("Multiple vaults found, set OBSIDIAN_VAULT to pick one: %s",
                 [str(s) for s in seen])
    return None


def _notes_dir() -> Path | None:
    v = find_vault()
    if not v:
        return None
    d = v / _SUBDIR
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        log.warning("Cannot create JARVIS notes folder: %s", exc)
        return None
    return d


def is_available() -> bool:
    return _notes_dir() is not None


def _slug(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower())
    s = re.sub(r"[\s_-]+", "-", s).strip("-")
    return s[:limit] or "note"


def save_note(content: str) -> str:
    """Save a note as Markdown. Returns filename or ''."""
    content = (content or "").strip()
    if not content:
        return ""
    d = _notes_dir()
    if not d:
        return ""
    ts = datetime.now()
    name = f"{ts:%Y-%m-%d-%H%M}-{_slug(content)}.md"
    body = (f"---\ncreated: {ts.isoformat(timespec='seconds')}\n"
            f"source: jarvis\n---\n\n{content}\n")
    try:
        (d / name).write_text(body, encoding="utf-8")
        log.info("Obsidian note saved: %s", name)
        return name
    except Exception as exc:
        log.warning("Obsidian save failed: %s", exc)
        return ""


def _read_one(path: Path) -> dict:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {"file": path.name, "content": "", "mtime": 0}
    body = re.sub(r"^---\n.*?\n---\n", "", text, flags=re.DOTALL).strip()
    if not body:
        body = text.strip()
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = 0
    return {"file": path.name, "content": body, "mtime": mtime}


def list_notes(limit: int = 5) -> list:
    d = _notes_dir()
    if not d:
        return []
    try:
        files = sorted(d.glob("*.md"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return []
    return [_read_one(p) for p in files[:limit]]


def search_notes(query: str, limit: int = 5) -> list:
    q = (query or "").strip().lower()
    if not q:
        return list_notes(limit=limit)
    d = _notes_dir()
    if not d:
        return []
    hits = []
    try:
        files = sorted(d.glob("*.md"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return []
    for p in files:
        n = _read_one(p)
        if q in n["content"].lower() or q in p.stem.lower():
            hits.append(n)
        if len(hits) >= limit:
            break
    return hits


def clear_notes() -> int:
    """Delete JARVIS notes from the vault. Returns count removed."""
    d = _notes_dir()
    if not d:
        return 0
    n = 0
    try:
        for p in d.glob("*.md"):
            try:
                p.unlink()
                n += 1
            except Exception:
                continue
    except Exception:
        pass
    if n:
        log.info("Obsidian notes cleared: %d", n)
    return n
