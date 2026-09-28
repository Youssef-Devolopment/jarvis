"""Clipboard watcher — detects content type, logs history, suggests actions."""

from __future__ import annotations
import re
import threading
import time
from datetime import datetime
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_CLIP_LOG = _ROOT / "logs" / "clipboard_history.log"

_thread = None
_stop = threading.Event()
_last_content = ""
_last_ts = 0.0
_recent = []
_recent_lock = threading.Lock()
_suggestions = []
_suggestions_lock = threading.Lock()

_URL_RE = re.compile(r"^https?://\S+$")
_EMAIL_RE = re.compile(r"^[\w\.\-]+@[\w\-]+\.[a-z]{2,}$", re.IGNORECASE)
_PHONE_RE = re.compile(r"^\+?\d[\d\s\-]{6,15}$")
_ERROR_HINTS = re.compile(r"(traceback|error:|exception|failed|error\s+\d{3}|errno)", re.IGNORECASE)
_CODE_HINTS = re.compile(r"(def\s+\w+|class\s+\w+|function\s+\w+|import\s+\w+|const\s+\w+|let\s+\w+)")
_ARABIC_RE = re.compile(r"[\u0600-\u06FF]")


def detect_type(text):
    if not text: return "empty"
    t = text.strip()
    if len(t) > 5000: return "text_long"
    if _URL_RE.match(t): return "url"
    if _EMAIL_RE.match(t): return "email"
    if _PHONE_RE.match(t) and len(t) < 20: return "phone"
    if _ERROR_HINTS.search(t[:500]): return "error"
    if _CODE_HINTS.search(t[:1000]): return "code"
    if _ARABIC_RE.search(t[:200]): return "arabic"
    if len(t) < 100: return "text_short"
    return "text"


def suggest_actions(ct, text):
    preview = text[:80].replace("\n", " ")
    sug = []
    if ct == "url":
        sug = [{"action": "summarize", "label": "Summarize this page"},
               {"action": "open", "label": "Open in browser"}]
    elif ct == "code":
        sug = [{"action": "explain_code", "label": "Explain this code"},
               {"action": "improve_code", "label": "Suggest improvements"},
               {"action": "save_snippet", "label": "Save as snippet"}]
    elif ct == "error":
        sug = [{"action": "explain_error", "label": "Explain this error"},
               {"action": "search_error", "label": "Search for a fix"}]
    elif ct == "arabic":
        sug = [{"action": "translate", "label": "Translate to English"}]
    elif ct == "text_long":
        sug = [{"action": "summarize", "label": "Summarize"}]
    for s in sug:
        s["preview"] = preview
        s["content_type"] = ct
        s["ts"] = datetime.now().isoformat(timespec="seconds")
    return sug


def _get_clip():
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except ImportError:
        try:
            import tkinter
            r = tkinter.Tk(); r.withdraw()
            t = r.clipboard_get(); r.destroy()
            return t or ""
        except Exception:
            return ""


def _loop():
    global _last_content, _last_ts
    log.info("Clipboard watcher started")
    while not _stop.is_set():
        try:
            txt = _get_clip()
            if txt and txt != _last_content:
                now = time.time()
                if now - _last_ts > 0.5:
                    _last_content = txt
                    _last_ts = now
                    ct = detect_type(txt)
                    if ct != "empty":
                        item = {"type": ct, "preview": txt[:120].replace("\n", " "),
                                "length": len(txt),
                                "ts": datetime.now().isoformat(timespec="seconds"),
                                "full": txt[:5000]}
                        with _recent_lock:
                            _recent.append(item)
                            if len(_recent) > 20: _recent.pop(0)
                        try:
                            with _CLIP_LOG.open("a", encoding="utf-8") as f:
                                f.write(f"[{item['ts']}] {ct} ({item['length']}): {item['preview'][:80]}\n")
                        except Exception: pass
                        sugs = suggest_actions(ct, txt)
                        if sugs:
                            with _suggestions_lock:
                                _suggestions.extend(sugs)
                                if len(_suggestions) > 10:
                                    _suggestions = _suggestions[-10:]
        except Exception as exc:
            log.debug("Clipboard loop error: %s", exc)
        _stop.wait(1.5)


def start():
    global _thread
    if _thread and _thread.is_alive(): return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="clipboard", daemon=True)
    _thread.start()


def stop(): _stop.set()


def recent(limit=10):
    with _recent_lock:
        return list(_recent[-limit:])


def pending_suggestions(consume=False):
    with _suggestions_lock:
        result = list(_suggestions)
        if consume: _suggestions.clear()
        return result
