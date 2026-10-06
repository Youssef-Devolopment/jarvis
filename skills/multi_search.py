"""Deep Web Intelligence — Parallel Multi-Query Explorer.

*"explore vector databases"* fans 4 query variants out at once across
the existing search tiers (Tavily/Brave/DDG/Bing/SearxNG), dedupes by
URL, and synthesizes ONE clean answer with sources — one round trip
instead of you juggling tabs.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from logger import get_logger
from skills.registry import register

log = get_logger(__name__)

_VARIANTS = 4


def _variants(topic: str) -> list[str]:
    t = topic.strip().rstrip("?!. ")
    return [t, f"{t} guide", f"{t} examples", f"{t} best practices"]


def explore(topic: str, search_fn=None) -> tuple[list[dict], int]:
    """Run the variants concurrently. Returns (unique_results, queries)."""
    if search_fn is None:
        from skills.web_search import search_all as search_fn
    results: list[dict] = []
    queries = 0
    with ThreadPoolExecutor(max_workers=_VARIANTS) as pool:
        futs = {pool.submit(search_fn, q): q for q in _variants(topic)}
        for fut in as_completed(futs):
            queries += 1
            try:
                hits = fut.result() or []
            except Exception as exc:
                log.debug("variant %r failed: %s", futs[fut], exc)
                continue
            results.extend(hits)
    seen, unique = set(), []
    for r in results:
        url = (r.get("url") or "").strip()
        key = url.rstrip("/").lower() or (r.get("title") or "")[:60]
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    unique.sort(key=lambda r: len(r.get("snippet") or ""), reverse=True)
    return unique[:10], queries


def _synthesize(topic: str, hits: list[dict]) -> str | None:
    """One LLM call over the merged hits. None when keyless/broken."""
    try:
        from ai.client import get_client
        c = get_client()
        blob = "\n".join(
            f"- {h.get('title', '')} ({h.get('url', '')})\n"
            f"  {(h.get('snippet') or '')[:220]}" for h in hits[:8])
        msgs = [
            {"role": "system",
             "content": ("You aggregate search results. In 2-4 sentences "
                         "answer the topic from the hits below, then add "
                         "up to 3 '- ' source lines (title + URL). If the "
                         "hits are useless, say so plainly.")},
            {"role": "user", "content": f"Topic: {topic}\n\n{blob}"[:5000]},
        ]
        out = []
        for kind, payload in c.stream(msgs):
            if kind == "content":
                out.append(payload)
        return "".join(out).strip() or None
    except Exception as exc:
        log.debug("explore synthesis skipped: %s", exc)
        return None


@register("multi_search", [
    r"^(?:please\s+)?explore\s+(?P<topic>.+?)[\?\.\!]?$",
    r"^(?:please\s+)?multi[-\s]?search\s+(?P<topic>.+?)[\?\.\!]?$",
    r"^cross[-\s]?check\s+(?P<topic>.+?)[\?\.\!]?$",
], "Fan out parallel searches and synthesize one answer", front=True)
def skill_explore(text, match):
    topic = (match.group("topic") or "").strip()
    if not topic:
        return None
    hits, queries = explore(topic)
    if not hits:
        return f"No results across {queries} parallel queries for '{topic}'."
    summary = _synthesize(topic, hits)
    if not summary:
        top = "\n".join(f"- {h.get('title', '?')} {h.get('url', '')}"
                        for h in hits[:3])
        summary = f"Top of {len(hits)} unique results:\n{top}"
    return (f"Explored {queries} queries → {len(hits)} unique results.\n"
            f"{summary}")[:2600]
