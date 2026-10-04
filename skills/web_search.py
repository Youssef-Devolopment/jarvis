"""Unified web search + fetch (merged brave/fast/deep variants).

Tiers, fastest first: Tavily AI search (key) -> duckduckgo_search
library -> Brave API (key) -> DDG lite -> DDG html scrape -> Bing ->
SearxNG. No browser needed. Page fetch falls back to the Jina
reader (keyless) when raw HTML yields nothing readable.
Helper names (_http_get, _strip_html, _search_ddg_html) are kept stable:
ai/search_agent.py imports them.
"""
from __future__ import annotations
import json
import os
import re
import urllib.parse
import urllib.request
from html import unescape
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS/1.0"
_HEADERS = {"User-Agent": _UA, "Accept": "text/html,application/json"}


def _http_get(url: str, timeout: float = 8.0) -> str | None:
    try:
        req = urllib.request.Request(url, headers=_HEADERS)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            charset = r.headers.get_content_charset() or "utf-8"
            return r.read().decode(charset, errors="ignore")
    except Exception as exc:
        log.debug("HTTP GET failed for %s: %s", url, exc)
        return None


def _strip_html(html: str) -> str:
    if not html:
        return ""
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<footer[^>]*>.*?</footer>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<header[^>]*>.*?</header>", " ", html,
                  flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"</(p|div|h[1-6]|li|br|tr)>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", " ", html)
    text = unescape(html)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def _search_ddg_lib(query: str, count: int = 5) -> list[dict]:
    """Official duckduckgo_search library tier."""
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS  # v8.x namespace
    except ImportError:
        log.debug("ddgs library missing")
        return []
    try:
        out = []
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=count) or []:
                title = (r.get("title") or "").strip()
                url = (r.get("href") or "").strip()
                if title and url:
                    out.append({"title": title[:150], "url": url,
                                "snippet": (r.get("body") or "")[:250]})
        return out
    except Exception as exc:
        log.debug("DDGS lib failed: %s", exc)
        return []


def _search_brave(query: str) -> list[dict]:
    key = os.getenv("BRAVE_API_KEY", "").strip()
    if not key:
        return []
    try:
        url = ("https://api.search.brave.com/res/v1/web/search?"
               + urllib.parse.urlencode({"q": query, "count": 5}))
        req = urllib.request.Request(url, headers={
            "X-Subscription-Token": key,
            "Accept": "application/json", "User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = []
        for item in ((data.get("web") or {}).get("results") or [])[:5]:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if title and url:
                out.append({"title": title[:150], "url": url,
                            "snippet": (item.get("description") or "")[:250]})
        return out
    except Exception as exc:
        log.debug("Brave failed: %s", exc)
        return []


def _search_ddg_lite(query: str) -> list[dict]:
    url = ("https://lite.duckduckgo.com/lite/?"
           + urllib.parse.urlencode({"q": query}))
    html = _http_get(url, timeout=10)
    if not html:
        return []
    results = []
    for m in re.finditer(
            r'<a[^>]+class="result-link"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL):
        link, title = m.group(1), _strip_html(m.group(2))
        if "duckduckgo" in link.lower():
            continue
        if title and link.startswith("http"):
            results.append({"title": title[:150], "url": link, "snippet": ""})
        if len(results) >= 6:
            break
    return results


def _search_ddg_html(query: str) -> list[dict]:
    url = ("https://html.duckduckgo.com/html/?"
           + urllib.parse.urlencode({"q": query}))
    html = _http_get(url, timeout=10)
    if not html:
        return []
    results = []
    for m in re.finditer(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL):
        link, title_html = m.group(1), m.group(2)
        uddg = re.search(r"uddg=([^&]+)", link)
        if uddg:
            link = urllib.parse.unquote(uddg.group(1))
        title = _strip_html(title_html)
        if title:
            results.append({"title": title, "url": link, "snippet": ""})
        if len(results) >= 6:
            break
    snippets = [_strip_html(s) for s in re.findall(
        r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)]
    for i, sn in enumerate(snippets):
        if i < len(results):
            results[i]["snippet"] = sn[:200]
    return results


def _search_bing(query: str) -> list[dict]:
    url = "https://www.bing.com/search?" + urllib.parse.urlencode({"q": query})
    html = _http_get(url, timeout=10)
    if not html:
        return []
    results = []
    for m in re.finditer(
            r'<h2><a[^>]+href="([^"]+)"[^>]*>(.*?)</a></h2>'
            r"(?:.*?<p[^>]*>(.*?)</p>)?", html, re.DOTALL):
        link = m.group(1)
        title = _strip_html(m.group(2))
        snippet = _strip_html(m.group(3) or "")
        if title and link.startswith("http"):
            results.append({"title": title[:150], "url": link,
                            "snippet": snippet[:250]})
        if len(results) >= 6:
            break
    return results


def _search_searx(query: str) -> list[dict]:
    mirrors = [
        "https://searx.be/search",
        "https://search.bus-hit.me/search",
        "https://searx.tiekoetter.com/search",
    ]
    for base in mirrors:
        url = base + "?" + urllib.parse.urlencode(
            {"q": query, "format": "json"})
        raw = _http_get(url, timeout=8)
        if not raw:
            continue
        try:
            data = json.loads(raw)
            results = []
            for r in (data.get("results") or [])[:6]:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "snippet": (r.get("content") or "")[:250],
                })
            if results:
                return results
        except Exception:
            continue
    return []


def search_all(query: str) -> list[dict]:
    """Try every provider until results. No browser needed."""
    for fn in (_search_tavily, _search_ddg_lib, _search_brave, _search_ddg_lite,
               _search_ddg_html, _search_bing, _search_searx):
        try:
            results = fn(query)
            if results:
                log.info("Search %s: %d results", fn.__name__, len(results))
                return results
        except Exception as exc:
            log.debug("%s failed: %s", fn.__name__, exc)
    return []


def _tavily_key() -> str:
    k = (os.getenv("TAVILY_API_KEY") or "").strip()
    if not k or k.startswith("tvly-paste") or len(k) < 8:
        return ""
    return k


def _search_tavily(query: str, count: int = 5) -> list[dict]:
    """Tavily AI search (keyed, fastest tier). Silent [] when keyless."""
    key = _tavily_key()
    if not key:
        return []
    try:
        body = json.dumps({"query": query, "search_depth": "fast",
                           "max_results": max(1, min(count, 10))}).encode()
        req = urllib.request.Request(
            "https://api.tavily.com/search", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8") or "{}")
        out = []
        for item in (data.get("results") or [])[:count]:
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()
            if title and url:
                out.append({"title": title[:150], "url": url,
                            "snippet": (item.get("content") or "")[:250]})
        return out
    except Exception as exc:
        log.debug("Tavily failed: %s", exc)
        return []


def fetch_page(url: str, max_chars: int = 4000) -> str:
    """Fetch and clean a web page. No browser. Falls back to the
    keyless Jina reader when raw HTML yields nothing readable."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    html = _http_get(url, timeout=12)
    if html:
        text = _strip_html(html)
        if len(text) >= 200:
            return text[:max_chars]
    try:
        md = _http_get("https://r.jina.ai/" + url, timeout=20)
        if md and len(md.strip()) >= 200:
            return md.strip()[:max_chars]
    except Exception as exc:
        log.debug("Jina reader failed: %s", exc)
    if html:
        return _strip_html(html)[:max_chars]
    return ""


@register("web_search", [
    r"^(?:please\s+)?(?:search(?:\s+(?:the\s+)?web)?(?:\s+for)?|"
    r"look\s+up|google|find\s+(?:me\s+)?(?:info\s+on|information\s+on)"
    r"|deep\s+search(?:\s+for)?)\s+(?P<q>.+?)[\?\.\!]?$",
], "Search the web (no browser)")
def s_search(text, m):
    query = (m.group("q") or "").strip(" ?.!")
    if not query or len(query) < 2:
        return None
    results = search_all(query)
    if not results:
        return f"I could not find results for '{query}'."
    lines = [f"Top results for '{query}':"]
    for i, r in enumerate(results[:4], 1):
        title = (r.get("title") or "").strip()[:120]
        snippet = (r.get("snippet") or "").strip()[:180]
        lines.append(f"{i}. {title}" + (f" — {snippet}" if snippet else ""))
    return " ".join(lines)


@register("fast_fetch", [
    r"^(?:fetch|read|get|open)\s+(?P<url>https?://\S+)[\?\.\!]?$",
], "Fetch a URL as text (no browser)")
def s_fetch(text, m):
    url = (m.group("url") or "").strip().rstrip(".,!?")
    if not url:
        return None
    body = fetch_page(url)
    if not body:
        return f"Could not read {url}."
    return body[:2500] + ("…" if len(body) > 2500 else "")
