"""Site index — bookmarks + frequent history from local browsers.

Reads Brave/Chrome/Edge profile data (bookmarks JSON always works;
history is copied first so the running browser's lock never blocks).
Cached to logs/site_index.json.
"""
from __future__ import annotations
import json
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_CACHE = _ROOT / "logs" / "site_index.json"
_MAX_AGE = 24 * 3600

_BROWSERS = {
    "brave": ("BraveSoftware", "Brave-Browser"),
    "chrome": ("Google", "Chrome"),
    "edge": ("Microsoft", "Edge"),
}


def _profiles(vendor: str, product: str) -> list:
    base = (Path.home() / "AppData" / "Local" / vendor / product
            / "User Data")
    if not base.is_dir():
        return []
    out = []
    try:
        for child in base.iterdir():
            if child.is_dir() and (child / "Bookmarks").exists():
                out.append(child)
    except Exception:
        pass
    return out


def _walk_bookmarks(node: dict, out: list) -> None:
    if not isinstance(node, dict):
        return
    if node.get("type") == "url" and node.get("url", "").startswith("http"):
        out.append({"title": (node.get("name") or "").strip(),
                    "url": node["url"].strip()})
        return
    for child in node.get("children", []) or []:
        _walk_bookmarks(child, out)


def _read_bookmarks() -> list:
    out = []
    for vendor, product in _BROWSERS.values():
        for profile in _profiles(vendor, product):
            try:
                data = json.loads((profile / "Bookmarks").read_text(
                    encoding="utf-8"))
                for root in (data.get("roots") or {}).values():
                    _walk_bookmarks(root, out)
            except Exception as exc:
                log.debug("bookmarks %s failed: %s", profile, exc)
    seen, uniq = set(), []
    for b in out:
        if b["url"] not in seen and b["title"]:
            seen.add(b["url"])
            uniq.append(b)
    return uniq


def _read_history(limit: int = 100) -> list:
    out = []
    for vendor, product in _BROWSERS.values():
        for profile in _profiles(vendor, product):
            src = profile / "History"
            if not src.exists():
                continue
            tmp = ""
            try:
                fd, tmp = tempfile.mkstemp(suffix=".db")
                import os as _os
                _os.close(fd)
                shutil.copy2(src, tmp)
                c = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
                rows = c.execute(
                    "SELECT url, title, visit_count FROM urls "
                    "WHERE url LIKE 'http%' "
                    "ORDER BY visit_count DESC LIMIT ?", (limit,)).fetchall()
                c.close()
                for url, title, visits in rows:
                    out.append({"title": (title or url)[:120], "url": url,
                                "visits": visits or 0})
            except Exception as exc:
                log.debug("history %s failed: %s", profile, exc)
            finally:
                try:
                    if tmp:
                        Path(tmp).unlink(missing_ok=True)
                except Exception:
                    pass
    return out


def _domain(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


def build_index() -> dict:
    bookmarks = _read_bookmarks()
    history = _read_history()
    data = {"built_at": time.time(), "bookmarks": bookmarks,
            "history": history}
    try:
        _CACHE.write_text(json.dumps(data, ensure_ascii=False),
                          encoding="utf-8")
    except Exception as exc:
        log.warning("site index cache failed: %s", exc)
    log.info("Site index: %d bookmarks, %d history",
             len(bookmarks), len(history))
    return data


def load_index() -> dict:
    try:
        if _CACHE.exists():
            data = json.loads(_CACHE.read_text(encoding="utf-8"))
            if time.time() - float(data.get("built_at", 0)) < _MAX_AGE:
                return data
    except Exception:
        pass
    return build_index()


def refresh() -> dict:
    return build_index()


def find(query: str) -> dict | None:
    """Best bookmark/history hit: exact title → domain → substring."""
    q = (query or "").strip().lower()
    if not q:
        return None
    data = load_index()
    pool = ([{**b, "kind": "bookmark"} for b in data.get("bookmarks", [])]
            + [{**h, "kind": "history"} for h in data.get("history", [])])
    for b in pool:
        if b["title"].lower() == q:
            return b
    for b in pool:
        dom = _domain(b["url"]).split(".")[0]
        if dom and (dom == q or (len(q) >= 4 and dom.startswith(q))):
            return b
    for b in pool:
        if q in b["title"].lower() or q in b["url"].lower():
            return b
    return None
