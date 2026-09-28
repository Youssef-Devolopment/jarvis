"""Invisible browser — controls Chromium headless. NO window on screen."""
from __future__ import annotations
import threading
import time
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_PROFILE = _ROOT / ".headless_profile"

_browser_lock = threading.Lock()
_context = None
_playwright = None


def _ensure_started():
    global _context, _playwright
    with _browser_lock:
        if _context is not None:
            return
        try:
            from playwright.sync_api import sync_playwright
            _PROFILE.mkdir(exist_ok=True)
            _playwright = sync_playwright().start()
            _context = _playwright.chromium.launch_persistent_context(
                user_data_dir=str(_PROFILE),
                headless=True,
                viewport={"width": 1280, "height": 800},
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-sync",
                ],
            )
            log.info("Headless browser launched")
        except Exception as exc:
            log.exception("Headless browser failed: %s", exc)
            _context = None


def _get_page():
    _ensure_started()
    if _context is None:
        return None
    pages = _context.pages
    return pages[0] if pages else _context.new_page()


def browse(url: str, wait: float = 1.0) -> str:
    page = _get_page()
    if page is None:
        return "[error] headless browser unavailable"
    try:
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(wait)
        return f"[ok] {page.title()} — {page.url}"
    except Exception as exc:
        return f"[error] {exc}"


def read_page(max_chars: int = 5000) -> str:
    page = _get_page()
    if page is None:
        return "[error] no browser"
    try:
        text = page.evaluate("""() => {
            const e = document.querySelector('article')
                   || document.querySelector('main')
                   || document.body;
            return e ? e.innerText : '';
        }""")
        text = (text or "").strip()
        return text[:max_chars] if text else "[empty page]"
    except Exception as exc:
        return f"[error] {exc}"


def search_google(query: str, max_results: int = 5) -> str:
    page = _get_page()
    if page is None:
        return "[error] no browser"
    try:
        import urllib.parse
        url = ("https://www.google.com/search?"
               + urllib.parse.urlencode({"q": query}))
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.5)
        results = page.evaluate("""(max) => {
            const out = [];
            const bad = h => /google\\.[a-z.]+\\/search/.test(h);
            for (const a of document.querySelectorAll('a')) {
                if (out.length >= max) break;
                const h = a.href || '';
                if (!h.startsWith('http') || bad(h)) continue;
                const t = (a.innerText || '').trim();
                if (t.length < 10) continue;
                const parent = a.closest('div');
                const snippet = parent ? (parent.innerText || '').trim().slice(0, 200) : '';
                out.push({title: t.slice(0, 150), url: h, snippet});
            }
            return out;
        }""", max_results)
        if not results:
            return f"[no results for '{query}']"
        lines = [f"Results for '{query}':"]
        for i, r in enumerate(results[:max_results], 1):
            lines.append(f"{i}. {r['title']}")
            if r.get("snippet"):
                lines.append(f"   {r['snippet'][:180]}")
        return "\n".join(lines)
    except Exception as exc:
        return f"[error] {exc}"


def click_link(match_text: str) -> str:
    page = _get_page()
    if page is None:
        return "[error] no browser"
    try:
        link = page.get_by_role("link", name=match_text).first
        link.click(timeout=8000)
        time.sleep(1)
        return f"[ok] clicked '{match_text}' — now at {page.url}"
    except Exception as exc:
        return f"[error] {exc}"


def close_browser():
    global _context, _playwright
    with _browser_lock:
        try:
            if _context:
                _context.close()
            if _playwright:
                _playwright.stop()
        except Exception:
            pass
        _context = None
        _playwright = None
        log.info("Headless browser closed")
