"""Deep Research Agent: search -> fetch -> structured report.

Pipeline per topic: `search_all` finds candidates, the top few URLs
are fetched (same-host one level deep, capped), text and code blocks
are extracted with BeautifulSoup, and the digest is synthesized —
via LLM when a key exists, extractively in skills-only mode.
Reports land in docs/research/*.md and a one-line summary is
remembered so later chats can recall it.

All I/O behind injectable params so tests never touch the network.
"""
from __future__ import annotations
import re
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = _ROOT / "docs" / "research"

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS-research/1.0"
_MAX_SOURCES = 4
_FETCH_TIMEOUT = 15
_MAX_PAGE_CHARS = 12000
_MAX_SUBPAGES = 3
_NOISE_SELECTORS = (
    "script, style, nav, footer, header, aside, form, "
    "[class*=ad], [id*=ad-], [id*=banner], .cookie, .popup, .modal"
)


def _slug(topic: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (topic or "report").lower()).strip("-")
    return (s[:50] or "report")


def search_sources(topic: str, k: int = _MAX_SOURCES,
                   search_fn=None) -> list[dict]:
    """Top-k {title, url, snippet} deduped by URL."""
    fn = search_fn
    if fn is None:
        from skills.web_search import search_all
        fn = search_all
    out, seen = [], set()
    try:
        for r in fn(topic) or []:
            url = (r.get("url") or "").strip()
            if not url or url in seen:
                continue
            if not url.lower().startswith(("http://", "https://")):
                continue
            seen.add(url)
            out.append({"title": (r.get("title") or url).strip(),
                        "url": url,
                        "snippet": (r.get("snippet") or "").strip()[:300]})
            if len(out) >= k:
                break
    except Exception as exc:
        log.warning("research search failed: %s", exc)
    return out


def _parse_page(html: str) -> tuple[str, list[str]]:
    """Strip layout noise -> (clean text, code blocks)."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.select(_NOISE_SELECTORS):
        tag.decompose()
    code = []
    for blk in soup.find_all(["pre", "code"]):
        txt = blk.get_text("\n", strip=True)
        if len(txt) >= 20 and len(code) < 12:
            code.append(txt[:1500])
        blk.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    fenced = re.findall(r"```(?:\w*\n)?(.+?)```", text, re.DOTALL)
    for f in fenced[:12 - len(code)]:
        if len(f.strip()) >= 20:
            code.append(f.strip()[:1500])
    return text[:_MAX_PAGE_CHARS], code


def _get(url: str, timeout: int = _FETCH_TIMEOUT) -> str:
    import requests
    r = requests.get(url, timeout=timeout,
                     headers={"User-Agent": _UA})
    r.raise_for_status()
    return r.text


def fetch_source(url: str, depth: int = 1, _seen: set | None = None,
                 raw_fn=None) -> dict:
    """Fetch a page (+ same-host links one level, capped). Safe:
    http(s) only, timeouts, size caps, no auth, no binaries."""
    from urllib.parse import urljoin, urlparse
    if _seen is None:
        _seen = set()
    out = {"url": url, "title": url, "text": "", "code": [],
           "subpages": 0}
    try:
        host = urlparse(url).netloc.lower()
        if urlparse(url).scheme not in ("http", "https") or not host:
            return out
        raw = raw_fn(url) if raw_fn else _get(url)
        if not raw or len(raw) > 2_000_000:
            return out
        text, code = _parse_page(raw)
        try:
            from bs4 import BeautifulSoup
            title = (BeautifulSoup(raw, "html.parser").title or "")
            title = title.get_text(strip=True) if title else ""
            if title:
                out["title"] = title[:150]
        except Exception:
            pass
        out["text"], out["code"] = text, code
        if depth > 0 and url not in _seen:
            _seen.add(url)
            try:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(raw, "html.parser")
                n = 0
                for a in soup.find_all("a", href=True):
                    if n >= _MAX_SUBPAGES:
                        break
                    link = urljoin(url, a["href"])
                    p = urlparse(link)
                    if (p.scheme not in ("http", "https")
                            or p.netloc.lower() != host
                            or link in _seen):
                        continue
                    _seen.add(link)
                    try:
                        sub = (raw_fn(link) if raw_fn
                               else _get(link))
                        st, sc = _parse_page(sub)
                        if st:
                            out["text"] += "\n\n---\n\n" + st[:3000]
                            out["code"] += sc[:2]
                            n += 1
                            out["subpages"] += 1
                    except Exception:
                        continue
                out["text"] = out["text"][:_MAX_PAGE_CHARS]
            except Exception:
                pass
    except Exception as exc:
        log.debug("research fetch failed %s: %s", url, exc)
    return out


def _default_llm(topic: str, digests: list[dict]) -> str | None:
    """One LLM call -> TL;DR + key points. None when keyless/broken."""
    try:
        from ai.client import get_client
        from config import get_settings
        s = get_settings()
        c = get_client()
        brief = "\n\n".join(
            f"SOURCE: {d['title']}\nURL: {d['url']}\n"
            f"{d['text'][:900]}" for d in digests)
        msgs = [
            {"role": "system",
             "content": ("You write terse technical briefs. Reply with a "
                         "'TL;DR:' line (1-2 sentences) then 3-6 '- ' key "
                         "points. No fluff.")},
            {"role": "user",
             "content": f"Topic: {topic}\n\n{brief}"[:6000]},
        ]
        out = []
        for kind, payload in c.stream(msgs):
            if kind == "content":
                out.append(payload)
        text = "".join(out).strip()
        return text or None
    except Exception as exc:
        log.debug("research LLM synthesis skipped: %s", exc)
        return None


def synthesize(topic: str, sources: list[dict],
               llm_fn=None) -> tuple[str, list[str]]:
    """Returns (tldr, key_points). Extractive fallback, no key needed."""
    if not sources:
        return f"No readable sources found for '{topic}'.", []
    if llm_fn is None:
        llm_fn = _default_llm
    try:
        brief = llm_fn(topic, sources)
    except Exception:
        brief = None
    if brief:
        lines = [ln.strip() for ln in brief.splitlines() if ln.strip()]
        tldr = lines[0]
        if tldr.lower().startswith("tl;dr"):
            tldr = tldr.split(":", 1)[-1].strip()
        points = [ln.lstrip("-*• ").strip()
                  for ln in lines[1:] if ln.startswith(("-", "*", "•"))]
        return tldr, points[:8]
    tldr = (f"Key material on '{topic}' from {len(sources)} sources "
            f"(offline digest — add an API key for an AI summary).")
    points = []
    for s in sources:
        first = (s.get("text") or "").split("\n", 1)[0].strip()[:220]
        if first:
            points.append(f"{s.get('title', '')}: {first}")
    return tldr, points[:8]


def write_report(topic: str, tldr: str, key_points: list[str],
                 sources: list[dict], out_dir: Path | None = None) -> Path:
    """Write the Markdown report. Returns the file path."""
    d = out_dir or OUT_DIR
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    ts = datetime.now()
    fp = d / f"{ts:%Y%m%d-%H%M}-{_slug(topic)}.md"
    parts = [f"# Research: {topic}",
             f"_{ts:%Y-%m-%d %H:%M} · JARVIS deep research · "
             f"{len(sources)} sources_",
             "", "## TL;DR", "", tldr, ""]
    if key_points:
        parts += ["## Key points", ""]
        parts += [f"- {p}" for p in key_points] + [""]
    parts += ["## Sources", ""]
    for i, s in enumerate(sources, 1):
        parts += [f"### {i}. {s.get('title', s.get('url'))}", "",
                  s.get("url", "")]
        body = (s.get("text") or "")[:800]
        if body:
            parts += ["", body]
        for blk in (s.get("code") or [])[:3]:
            parts += ["", "```", blk, "```"]
        parts += [""]
    parts += ["## Links"]
    for s in sources:
        parts += [f"- [{s.get('title', s.get('url'))}]({s.get('url')})"]
    parts += [""]
    fp.write_text("\n".join(parts), encoding="utf-8")
    return fp


def research_topic(topic: str, out_dir: Path | None = None,
                   max_sources: int = _MAX_SOURCES,
                   search_fn=None, fetch_fn=None, llm_fn=None,
                   remember_summary: bool = True) -> dict:
    """Full loop. Returns {ok, path, tldr, sources, error}."""
    topic = (topic or "").strip()
    if not topic:
        return {"ok": False, "error": "Empty topic."}
    found = search_sources(topic, k=max_sources, search_fn=search_fn)
    if not found:
        return {"ok": False,
                "error": f"No search results for '{topic}'."}
    fetched = []
    for r in found:
        try:
            f = fetch_fn(r["url"]) if fetch_fn else fetch_source(r["url"])
            f = dict(f)
            f.setdefault("title", r["title"])
            if not f.get("text") and r.get("snippet"):
                f["text"] = r["snippet"]
            if f.get("text"):
                fetched.append(f)
        except Exception as exc:
            log.debug("research source skipped %s: %s", r["url"], exc)
    if not fetched:
        return {"ok": False,
                "error": f"Sources found but none readable for '{topic}'."}
    tldr, points = synthesize(topic, fetched, llm_fn=llm_fn)
    try:
        path = write_report(topic, tldr, points, fetched,
                            out_dir=out_dir)
    except Exception as exc:
        return {"ok": False, "error": f"Could not save report: {exc}"}
    if remember_summary:
        try:
            from memory import remember as _remember
            _remember(f"Research on {topic}: {tldr[:220]} "
                      f"(report: {path})", category="research",
                      source="research-agent")
        except Exception as exc:
            log.debug("research remember failed: %s", exc)
    log.info("Research done: %s (%d sources)", path, len(fetched))
    return {"ok": True, "path": str(path), "tldr": tldr,
            "sources": len(fetched)}


_jobs: dict = {}
_jobs_lock = threading.Lock()
_MAX_JOBS = 20


def _prune_jobs() -> None:
    """Drop oldest finished jobs past the cap. Call with lock held."""
    done = sorted((j for j in _jobs.values() if j.get("status") == "done"),
                  key=lambda j: j.get("started", 0))
    for old in done[:max(0, len(done) - _MAX_JOBS)]:
        _jobs.pop(old["id"], None)


def start_research(topic: str, **kwargs) -> dict:
    """Async trigger: worker thread, poll via job_status()."""
    jid = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[jid] = {"id": jid, "topic": topic, "status": "running",
                      "started": time.time(), "result": None}
        _prune_jobs()
    threading.Thread(target=_run_job, args=(jid, topic, kwargs),
                     daemon=True, name=f"research-{jid}").start()
    return {"id": jid, "topic": topic, "status": "running"}


def _run_job(jid: str, topic: str, kwargs: dict) -> None:
    try:
        res = research_topic(topic, **kwargs)
    except Exception as exc:
        res = {"ok": False, "error": str(exc)[:200]}
    with _jobs_lock:
        if jid in _jobs:
            _jobs[jid]["status"] = "done"
            _jobs[jid]["result"] = res
    try:
        from system import notify
        if res.get("ok"):
            notify.alert("Research ready", str(topic)[:100])
        else:
            notify.alert("Research failed",
                         str(res.get("error") or topic)[:120])
    except Exception:
        pass


def job_status(jid: str) -> dict | None:
    with _jobs_lock:
        job = _jobs.get(jid)
        return dict(job) if job else None
