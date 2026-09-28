"""Folder sentinel — react when files land in watched folders.

Opt-in only: nothing is watched until the user says
"watch my downloads". Backed by watchdog when installed,
otherwise the skill replies with an install hint.
"""
from __future__ import annotations
import threading
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_lock = threading.Lock()
_observer = None
_handler = None
_watching: set = set()
_watches: dict = {}

_SKIP_SUFFIX = (".tmp", ".part", ".crdownload", ".download", ".lock")
_SKIP_PREFIX = ("~", ".")


def _has_watchdog() -> bool:
    try:
        import watchdog  # noqa: F401
        return True
    except ImportError:
        return False


def _should_ignore(path: str) -> bool:
    name = Path(path).name
    if name.startswith(_SKIP_PREFIX):
        return True
    if name.lower().endswith(_SKIP_SUFFIX):
        return True
    return False


def _on_created(path: str) -> None:
    """Lightweight handler — runs in the observer thread, no LLM here."""
    if _should_ignore(path):
        return
    msg = f"New file arrived: {path}"
    log.info("Sentinel: %s", msg)
    try:
        from memory import context as ctx
        ctx.log_event("file", msg[:200])
    except Exception:
        pass


def _ensure_observer():
    global _observer, _handler
    if _observer is not None:
        return _observer
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    class _Handler(FileSystemEventHandler):
        def on_created(self, event):
            try:
                _on_created(event.src_path)
            except Exception as exc:
                log.debug("Sentinel handler failed: %s", exc)

    _handler = _Handler()
    _observer = Observer()
    _observer.start()
    return _observer


def _persist() -> None:
    try:
        from memory import set_pref, get_pref
        set_pref("sentinel_folders", sorted(_watching))
        set_pref("sentinel_enabled", bool(_watching))
    except Exception:
        pass


def watch(path: str) -> str:
    if not _has_watchdog():
        return "Folder watching needs the watchdog package. Run: pip install watchdog"
    p = str(Path(path).expanduser().resolve())
    if not Path(p).is_dir():
        return f"Not a folder: {path}"
    with _lock:
        if p in _watching:
            return f"Already watching: {p}"
        try:
            obs = _ensure_observer()
            _watches[p] = obs.schedule(_handler, p, recursive=False)
            _watching.add(p)
        except Exception as exc:
            log.warning("Watch failed for %s: %s", p, exc)
            return f"Could not watch {p}."
    _persist()
    log.info("Sentinel watching: %s", p)
    return f"Watching {p} — I'll flag new files as they land."


def unwatch(path: str = "") -> str:
    with _lock:
        if not _watching:
            return "Not watching any folders."
        if path:
            p = str(Path(path).expanduser().resolve())
            if p not in _watching:
                return f"Wasn't watching: {p}"
            targets = [p]
        else:
            targets = sorted(_watching)
        for p in targets:
            try:
                if _observer is not None and p in _watches:
                    _observer.unschedule(_watches.pop(p))
            except Exception:
                pass
            _watching.discard(p)
            _watches.pop(p, None)
    _persist()
    return "Stopped watching: " + ", ".join(targets)


def watched() -> str:
    with _lock:
        items = sorted(_watching)
    if not items:
        return "Not watching any folders. Say 'watch my downloads' to start."
    return "Watching:\n" + "\n".join(f"  - {p}" for p in items)


def start_saved() -> int:
    """Re-watch persisted folders at boot. Returns count started."""
    try:
        from memory import get_pref
        if not get_pref("sentinel_enabled", False):
            return 0
        folders = get_pref("sentinel_folders", []) or []
    except Exception:
        return 0
    if not folders or not _has_watchdog():
        return 0
    n = 0
    for f in folders:
        try:
            if watch(str(f)).startswith("Watching"):
                n += 1
        except Exception:
            continue
    return n


@register("watch_folder", [
    r"^(?:watch|monitor)\s+(?:my\s+)?(?P<path>.+?)[\?\.\!]?$",
], "Watch a folder for new files")
def s_watch(text, m):
    raw = (m.group("path") or "").strip()
    shortcuts = {"downloads": str(Path.home() / "Downloads"),
                 "desktop": str(Path.home() / "Desktop"),
                 "documents": str(Path.home() / "Documents")}
    return watch(shortcuts.get(raw.lower(), raw))


@register("unwatch_folder", [
    r"^(?:stop\s+watching|unwatch)(?:\s+(?P<path>.+?))?[\?\.\!]?$",
], "Stop watching folders")
def s_unwatch(text, m):
    raw = ((m.group("path") or "").strip() if m else "")
    return unwatch(raw)


@register("list_watched", [
    r"^(?:what\s+are\s+you\s+watching|list\s+watched(?:\s+folders)?)[\?\.\!]?$",
], "List watched folders")
def s_watched(text, m):
    return watched()
