"""Deep search agent — multi-step research."""
from __future__ import annotations
import json
import os
import re
import time
from logger import get_logger

log = get_logger(__name__)

_MAX_ROUNDS = 3
_MAX_QUERIES_PER_ROUND = 3
_RESULTS_PER_QUERY = 5
_TOP_PAGES_TO_READ = 3


def _get_llm():
    from ai.client import get_client
    return get_client()


def _ask_llm(system: str, user: str, max_tokens: int = 300,
             temperature: float = 0.2) -> str:
    try:
        c = _get_llm()
        r = c._client.chat.completions.create(
            model=c.model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception as exc:
        log.exception("LLM call failed")
        return ""


def _plan_queries(question: str, prev_queries: list) -> list:
    system = (
        "You are a search query planner. Break the user's question into "
        "1 to 3 short, specific search queries (3-8 words each). "
        "Return ONLY a JSON array of strings. No explanation."
    )
    avoid = ""
    if prev_queries:
        avoid = ("\n\nDo NOT reuse these queries: "
                 + ", ".join(prev_queries))
    user = f"Question: {question}{avoid}"
    raw = _ask_llm(system, user, max_tokens=150, temperature=0.1)
    try:
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            arr = json.loads(m.group(0))
            queries = [str(x).strip() for x in arr if str(x).strip()]
            return queries[:_MAX_QUERIES_PER_ROUND]
    except Exception:
        pass
    return [question[:100]]


def _run_search(query: str) -> list:
    results = []
    brave_key = os.getenv("BRAVE_API_KEY", "").strip()
    if brave_key:
        try:
            import urllib.parse
            import urllib.request
            url = ("https://api.search.brave.com/res/v1/web/search?"
                   + urllib.parse.urlencode({"q": query, "count": 5}))
            req = urllib.request.Request(url, headers={
                "X-Subscription-Token": brave_key,
                "Accept": "application/json",
                "User-Agent": "JARVIS/1.0"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
                web = (data.get("web") or {}).get("results") or []
                for item in web[:5]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": (item.get("description") or "")[:300],
                    })
                if results:
                    return results
        except Exception as exc:
            log.debug("Brave failed: %s", exc)
    try:
        from skills.web_search import _search_ddg_html
        for r in _search_ddg_html(query)[:5]:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", ""),
            })
    except Exception as exc:
        log.debug("DDG failed: %s", exc)
    return results


def _read_page(url: str, max_chars: int = 3000) -> str:
    try:
        from skills.web_search import _http_get, _strip_html
        html = _http_get(url, timeout=10)
        if not html:
            return ""
        text = _strip_html(html)
        return text[:max_chars]
    except Exception as exc:
        log.debug("Page read failed: %s", exc)
        return ""


def _synthesize(question: str, evidence: list) -> str:
    if not evidence:
        return ""
    lines = []
    for i, e in enumerate(evidence, 1):
        title = e.get("title", "")
        url = e.get("url", "")
        content = (e.get("content") or e.get("snippet", ""))[:1500]
        lines.append(f"[{i}] {title}\nURL: {url}\n{content}\n")
    context = "\n---\n".join(lines)
    system = (
        "You are JARVIS answering from web search results. "
        "Use ONLY the evidence below. Do not add outside facts. "
        "Answer in 2-4 short spoken sentences. Cite sources as [1], [2]. "
        "If evidence does not answer, say so. No markdown, plain prose."
    )
    user = f"Question: {question}\n\nEvidence:\n{context}"
    return _ask_llm(system, user, max_tokens=400, temperature=0.2)


def _is_weak(answer: str) -> bool:
    if not answer:
        return True
    low = answer.lower()
    triggers = [
        "i could not find", "i couldn't find", "no information",
        "not enough information", "cannot answer", "unable to find",
        "evidence does not", "insufficient",
    ]
    return any(t in low for t in triggers)


def deep_search(question: str) -> str:
    if not question or not question.strip():
        return "[error] empty question"
    question = question.strip()
    log.info("deep_search: %r", question[:80])
    t0 = time.time()
    all_evidence = []
    tried_queries = []
    final_answer = ""
    for round_num in range(1, _MAX_ROUNDS + 1):
        queries = _plan_queries(question, tried_queries)
        for q in queries:
            tried_queries.append(q)
            results = _run_search(q)
            log.info("  %r -> %d results", q, len(results))
            for r in results[:_RESULTS_PER_QUERY]:
                r["content"] = r.get("snippet", "")
                all_evidence.append(r)
            if round_num == 1 and len(results) >= 1:
                for r in results[:_TOP_PAGES_TO_READ]:
                    if not r.get("url"):
                        continue
                    body = _read_page(r["url"])
                    if body and len(body) > 200:
                        for e in all_evidence:
                            if e.get("url") == r["url"]:
                                e["content"] = body
                                break
        if not all_evidence:
            continue
        final_answer = _synthesize(question, all_evidence)
        if final_answer and not _is_weak(final_answer):
            break
    elapsed = time.time() - t0
    log.info("deep_search done in %.1fs", elapsed)
    if not final_answer:
        return ("I searched multiple times but could not find a clear "
                "answer, sir. Want me to try a different angle?")
    top_urls = []
    seen = set()
    for e in all_evidence:
        u = e.get("url")
        if u and u not in seen:
            seen.add(u)
            top_urls.append(u)
        if len(top_urls) >= 3:
            break
    if top_urls:
        final_answer += "\n\nSources:\n" + "\n".join(
            f"  [{i+1}] {u}" for i, u in enumerate(top_urls))
    return final_answer
