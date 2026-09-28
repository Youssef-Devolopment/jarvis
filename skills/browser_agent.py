from __future__ import annotations
import concurrent.futures, queue, threading, time
from pathlib import Path
from urllib.parse import quote
from config import get_settings
from errors import BrowserError
from logger import get_logger

log = get_logger(__name__)

try:
    from playwright.sync_api import sync_playwright, Error as PWError
    _HAS = True
except ImportError:
    _HAS = False
    sync_playwright = None
    PWError = Exception

_ROOT = Path(__file__).resolve().parent.parent
_PROFILE = _ROOT / ".browser_profile"
_SHOTS = _ROOT / "logs" / "screenshots"
_READY = threading.Event()
_START_TIMEOUT = 60
_ACTION_TIMEOUT = 60
_LAST_ERROR: str = ""


class BrowserAgent:
    def __init__(self):
        self._q = queue.Queue()
        self._t = None
        self._lock = threading.Lock()
        self._started = False
        self._settings = get_settings()

    def last_error(self) -> str:
        return _LAST_ERROR

    def prewarm(self):
        """Launch Chromium in the background so first search is instant."""
        try:
            self._ensure_started()
            log.info("Browser pre-warmed.")
        except Exception as exc:
            log.warning("Prewarm failed: %s", exc)

    def _ensure_started(self):
        global _LAST_ERROR
        with self._lock:
            if self._started: return
            if not _HAS:
                _LAST_ERROR = "playwright-python not installed"
                raise BrowserError("Playwright not installed.",
                    detail="pip install playwright && playwright install chromium")
            _PROFILE.mkdir(exist_ok=True)
            _SHOTS.mkdir(parents=True, exist_ok=True)
            _READY.clear()
            self._t = threading.Thread(target=self._worker, name="browser", daemon=True)
            self._t.start()
            if not _READY.wait(timeout=_START_TIMEOUT):
                _LAST_ERROR = "browser startup timeout"
                raise BrowserError("Browser did not start in time.",
                    detail=f"Timeout after {_START_TIMEOUT}s. Try: playwright install chromium")

    def _worker(self):
        global _LAST_ERROR
        try:
            with sync_playwright() as p:
                log.info("Launching Chromium (headless=%s)...", self._settings.browser_headless)
                ctx = p.chromium.launch_persistent_context(
                    user_data_dir=str(_PROFILE),
                    headless=self._settings.browser_headless,
                    viewport={"width": 1280, "height": 800},
                    args=["--disable-blink-features=AutomationControlled",
                          "--no-sandbox",
                          "--disable-dev-shm-usage",
                          "--disable-gpu",
                          "--disable-extensions",
                          "--disable-background-networking",
                          "--disable-sync"])
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                handlers = self._make(ctx, page)
                _READY.set()
                log.info("Chromium ready.")
                while True:
                    job = self._q.get()
                    if job is None: break
                    action, kwargs, fut = job
                    try:
                        fut.set_result(handlers[action](**kwargs))
                    except Exception as exc:
                        log.exception("Action '%s' failed", action)
                        fut.set_exception(exc)
        except Exception as exc:
            _LAST_ERROR = f"launch failed: {exc}"
            log.exception("Browser worker crashed")
            _READY.set()

    def _make(self, ctx, page):
        eng = self._settings.browser_engine

        def do_nav(url):
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            try:
                page.goto(url, wait_until="commit", timeout=15000)
            except Exception as exc:
                log.warning("goto timeout/error: %s — trying webbrowser fallback", exc)
                try:
                    import webbrowser
                    webbrowser.open(url)
                    return {"url": url, "title": "Opened in default browser",
                            "fallback": True}
                except Exception:
                    raise
            return {"url": page.url, "title": page.title()}

        def do_search(query, engine_override=""):
            e = (engine_override or eng).lower()
            if e == "google":
                u = f"https://www.google.com/search?q={quote(query)}"
            elif e == "bing":
                u = f"https://www.bing.com/search?q={quote(query)}"
            else:
                u = f"https://duckduckgo.com/?q={quote(query)}"
            try:
                page.goto(u, wait_until="commit", timeout=15000)
            except Exception as exc:
                log.warning("search goto failed: %s", exc)
                try:
                    import webbrowser
                    webbrowser.open(u)
                    return {"url": u, "title": "Opened in browser",
                            "query": query, "engine": e, "results": [],
                            "fallback": True}
                except Exception:
                    raise
            try:
                # wait briefly for results to populate
                page.wait_for_timeout(600)
                res = page.evaluate("""() => {
                    const bad = h => /duckduckgo\\.com|google\\.[a-z.]+\\/search|bing\\.com\\/search/.test(h);
                    const as = Array.from(document.querySelectorAll('a'))
                        .filter(a => { const h=a.href||''; return h.startsWith('http') && !bad(h) && (a.innerText||'').trim().length>8; });
                    const seen = new Set(); const out=[];
                    for (const a of as) {
                        if (out.length>=5) break;
                        const h = a.href.split('#')[0];
                        if (seen.has(h)) continue;
                        seen.add(h);
                        out.push({title:(a.innerText||'').trim().slice(0,160), url:h});
                    }
                    return out;
                }""")
            except Exception:
                res = []
            return {"url": page.url, "title": page.title(), "query": query,
                    "engine": e, "results": res[:5]}

        def do_text(max_chars=4000):
            try:
                t = page.evaluate("""() => {
                    const e = document.querySelector('article') || document.querySelector('main') || document.body;
                    return e ? e.innerText : '';
                }""")
            except Exception:
                t = ""
            return {"url": page.url, "title": page.title(),
                    "text": (t or "").strip()[:max_chars]}

        def do_url():
            return {"url": page.url, "title": page.title()}

        def do_shot(full_page=False):
            ts = time.strftime("%Y%m%d_%H%M%S")
            p = _SHOTS / f"shot_{ts}.png"
            page.screenshot(path=str(p), full_page=full_page)
            return {"path": str(p), "url": page.url}

        def do_type_text(text, delay=30):
            page.keyboard.type(text, delay=delay)
            return {"typed": text}

        def do_press_key(key):
            page.keyboard.press(key)
            return {"pressed": key}

        def do_scroll(direction):
            if direction == "top":
                page.evaluate("window.scrollTo(0, 0)")
            elif direction == "bottom":
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            elif direction == "up":
                page.mouse.wheel(0, -500)
            else:
                page.mouse.wheel(0, 500)
            return {"scrolled": direction}

        def do_new_tab():
            ctx.new_page()
            return {"tab": "new"}

        def do_close_tab():
            page.close()
            return {"tab": "closed"}

        def do_back():
            page.go_back(timeout=10000)
            return {"url": page.url}

        def do_forward():
            page.go_forward(timeout=10000)
            return {"url": page.url}

        def do_reload():
            page.reload(timeout=10000)
            return {"url": page.url}

        return {"navigate": do_nav, "search": do_search, "get_text": do_text,
                "get_url": do_url, "screenshot": do_shot,
                "type_text": do_type_text,
                "press_key": do_press_key,
                "scroll": do_scroll,
                "new_tab": do_new_tab,
                "close_tab": do_close_tab,
                "back": do_back,
                "forward": do_forward,
                "reload": do_reload}

    def _submit(self, action, **kw):
        self._ensure_started()
        fut = concurrent.futures.Future()
        self._q.put((action, kw, fut))
        try:
            return fut.result(timeout=_ACTION_TIMEOUT)
        except concurrent.futures.TimeoutError:
            raise BrowserError(f"'{action}' timed out.")
        except PWError as exc:
            raise BrowserError(f"Browser error in '{action}'.", detail=str(exc))

    def navigate(self, url): return self._submit("navigate", url=url)
    def search(self, q, engine=""): return self._submit("search", query=q, engine_override=engine)
    def get_text(self, max_chars=4000): return self._submit("get_text", max_chars=max_chars)
    def get_url(self): return self._submit("get_url")
    def screenshot(self, full_page=False): return self._submit("screenshot", full_page=full_page)

    def type_text(self, text: str, delay: int = 30):
        return self._submit("type_text", text=text, delay=delay)

    def press_key(self, key: str):
        return self._submit("press_key", key=key)

    def scroll(self, direction: str):
        return self._submit("scroll", direction=direction)

    def new_tab(self):
        return self._submit("new_tab")

    def close_tab(self):
        return self._submit("close_tab")

    def back(self):
        return self._submit("back")

    def forward(self):
        return self._submit("forward")

    def reload(self):
        return self._submit("reload")


_agent = None
_lock = threading.Lock()


def get_agent() -> BrowserAgent:
    global _agent
    if _agent is None:
        with _lock:
            if _agent is None:
                _agent = BrowserAgent()
    return _agent
