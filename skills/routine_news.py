"""News headlines via NewsAPI."""
from __future__ import annotations
import json, os, urllib.parse, urllib.request
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _key():
    return os.getenv("NEWS_API_KEY")


@register("news", [
    r"^(?:what(?:'s| is)\s+)?(?:the\s+)?(?:news|headlines?)"
    r"(?:\s+(?:about|on)\s+(?P<t1>.+?))?[\?\.\!]?$",
    r"^(?:latest|today(?:'s)?)\s+news(?:\s+about\s+(?P<t2>.+?))?[\?\.\!]?$",
], "News headlines")
def s_news(text, m):
    if not _key():
        return "News API key not set. Add NEWS_API_KEY to .env."
    gd = m.groupdict()
    topic = (gd.get("t1") or gd.get("t2") or "").strip()
    try:
        if topic:
            url = ("https://newsapi.org/v2/everything?"
                   + urllib.parse.urlencode({
                       "q": topic, "sortBy": "publishedAt",
                       "pageSize": 5, "language": "en"}))
        else:
            url = ("https://newsapi.org/v2/top-headlines?"
                   + urllib.parse.urlencode({"country": "us", "pageSize": 5}))
        req = urllib.request.Request(url, headers={
            "X-Api-Key": _key(), "User-Agent": "JARVIS/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode("utf-8"))
        arts = d.get("articles") or []
        if not arts:
            return f"No news found{' about ' + topic if topic else ''}."
        lines = [f"Top {len(arts)} headlines:"]
        for i, a in enumerate(arts[:5], 1):
            t = (a.get("title") or "").strip()
            src = (a.get("source") or {}).get("name", "")
            if len(t) > 90:
                t = t[:87] + "..."
            lines.append(f"{i}. {t}" + (f" — {src}" if src else ""))
        return " ".join(lines)
    except Exception as exc:
        return f"News failed: {str(exc)[:80]}"
