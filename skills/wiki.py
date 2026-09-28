"""Wikipedia summaries via REST API (no key)."""
from __future__ import annotations
import re
import urllib.parse
from skills.registry import register
from skills.http_util import http_get
from logger import get_logger

log = get_logger(__name__)


@register("wiki", [
    r"\b(?:tell\s+me\s+about|what\s+is|what'?s|who\s+(?:is|was)|define)\s+"
    r"(?P<q>.+?)[\?\.\!]?$",
    r"\bwikipedia\s+(?:search\s+)?(?P<q2>.+?)[\?\.\!]?$",
], "Wikipedia lookup")
def skill_wiki(text, m):
    gd = m.groupdict()
    query = (gd.get("q") or gd.get("q2") or "").strip(" ?.!,")
    if not query or len(query) < 2 or len(query) > 100:
        return None
    # Skip if the query is clearly math or a command
    if re.fullmatch(r"[\d\s\+\-\*/\.]+", query):
        return None
    try:
        search = http_get("https://en.wikipedia.org/w/api.php?"
                      + urllib.parse.urlencode({
                          "action": "query", "list": "search",
                          "srsearch": query, "srlimit": 1, "format": "json"}), as_json=True)
        hits = (search.get("query") or {}).get("search") or []
        if not hits:
            return None
        title = hits[0]["title"]
        summary = http_get("https://en.wikipedia.org/api/rest_v1/page/summary/"
                       + urllib.parse.quote(title.replace(" ", "_")), as_json=True)
        extract = (summary.get("extract") or "").strip()
        if not extract:
            return None
        sentences = re.split(r"(?<=[.!?])\s+", extract)
        out = " ".join(sentences[:2])
        if len(out) > 400:
            out = out[:397].rsplit(" ", 1)[0] + "..."
        return out
    except Exception as exc:
        log.debug("Wiki failed: %s", exc)
        return None
