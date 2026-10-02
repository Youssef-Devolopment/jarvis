"""App index — auto-discovered programs with exact paths.

Sources: running processes (exe paths), Start Menu shortcuts,
Desktop shortcuts, pinned taskbar items. Cached to
logs/app_index.json, rebuilt when older than 24h or on demand.
"""
from __future__ import annotations
import difflib
import json
import os
import time
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_CACHE = _ROOT / "logs" / "app_index.json"
_MAX_AGE = 24 * 3600


def _clean(name: str) -> str:
    n = (name or "").lower().strip()
    if n.endswith(".lnk"):
        n = n[:-4]
    if n.endswith(".exe"):
        n = n[:-4]
    return n.replace("_", " ").replace("-", " ").strip()


def _lnk_target(path: Path) -> str:
    try:
        import pythoncom
        from win32com.client import Dispatch
        pythoncom.CoInitialize()
        sc = Dispatch("WScript.Shell").CreateShortCut(str(path))
        return (sc.TargetPath or "").strip()
    except Exception:
        return ""


def _scan_lnk_dir(folder: Path, source: str, out: list) -> None:
    if not folder.is_dir():
        return
    try:
        for p in folder.rglob("*.lnk"):
            target = _lnk_target(p)
            if not target:
                continue
            out.append({"name": _clean(p.stem), "path": target,
                        "source": source, "link": str(p)})
    except Exception as exc:
        log.debug("lnk scan %s failed: %s", folder, exc)


def _scan_running(out: list) -> None:
    try:
        import psutil
    except ImportError:
        return
    seen = set()
    try:
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                exe = proc.info.get("exe") or ""
                name = proc.info.get("name") or ""
            except Exception:
                continue
            if not exe or not name:
                continue
            key = exe.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({"name": _clean(Path(exe).stem), "path": exe,
                        "source": "running", "link": ""})
    except Exception as exc:
        log.debug("process scan failed: %s", exc)


def _scan() -> list:
    out: list = []
    _scan_running(out)
    appdata = os.getenv("APPDATA") or ""
    progdata = os.getenv("PROGRAMDATA") or ""
    home = Path.home()
    _scan_lnk_dir(Path(progdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
                  "startmenu", out)
    _scan_lnk_dir(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
                  "startmenu", out)
    _scan_lnk_dir(home / "Desktop", "desktop", out)
    _scan_lnk_dir(Path(appdata) / "Microsoft" / "Internet Explorer" / "Quick Launch"
                  / "User Pinned" / "TaskBar", "taskbar", out)
    # Deduplicate: keep first hit per path, prefer non-running source.
    best: dict = {}
    rank = {"startmenu": 0, "desktop": 1, "taskbar": 2, "running": 3}
    for e in out:
        if not e["name"] or not e["path"]:
            continue
        k = e["path"].lower()
        if k not in best or rank.get(e["source"], 9) < rank.get(best[k]["source"], 9):
            best[k] = e
    return sorted(best.values(), key=lambda e: e["name"])


def build_index() -> list:
    apps = _scan()
    try:
        _CACHE.write_text(json.dumps(
            {"built_at": time.time(), "apps": apps}, ensure_ascii=False),
            encoding="utf-8")
    except Exception as exc:
        log.warning("app index cache failed: %s", exc)
    log.info("App index: %d apps", len(apps))
    return apps


def load_index() -> list:
    try:
        if _CACHE.exists():
            data = json.loads(_CACHE.read_text(encoding="utf-8"))
            if time.time() - float(data.get("built_at", 0)) < _MAX_AGE:
                return data.get("apps", [])
    except Exception:
        pass
    return build_index()


def refresh() -> list:
    return build_index()


def find(query: str) -> dict | None:
    """Best index hit for a name, or None."""
    q = _clean(query)
    if not q:
        return None
    apps = load_index()
    names = [a["name"] for a in apps]
    for a in apps:
        if a["name"] == q:
            return a
    for a in apps:
        if a["name"].startswith(q) or q in a["name"]:
            return a
    close = difflib.get_close_matches(q, names, n=1, cutoff=0.7)
    if close:
        return next(a for a in apps if a["name"] == close[0])
    # fall back to exe-stem match (e.g. "code" → "code.exe" owners)
    for a in apps:
        stem = Path(a["path"]).stem.lower()
        if stem == q or stem.startswith(q):
            return a
    return None
