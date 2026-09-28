"""Open ANY url as a REAL tab in your browser."""
import re
from skills.registry import register


@register("web_open", [
    r"^(?:please\s+)?(?:open|go\s+to|navigate\s+to|visit|bring\s+up)\s+(?P<t>.+?)[\?\.\!]?$",
], "Open a website in your browser")
def skill(text, match):
    from system import launch as L
    t = match.group("t").strip(" ?.!")
    if not t:
        return None
    if "pod bay door" in t.lower():
        return "I am sorry, Dave. I am afraid I cannot do that."
    if L.is_blocked_scheme(t):
        log_msg = f"Refused blocked scheme: {t[:60]}"
        try:
            from logger import get_logger
            get_logger(__name__).warning(log_msg)
        except Exception:
            pass
        return "Refused: that link type is blocked for safety."
    out = L.open_url(t)
    if out:
        return out
    # Not a url at all -> silent headless search, then open top hit.
    try:
        from skills.browser_agent import get_agent
        d = get_agent().search(t)
        rs = d.get("results") or []
        if not rs:
            return f"Could not find a site called {t}."
        top = rs[0].get("url") or ""
        if top:
            return L.open_url(top) or f"Top hit: {top}"
        return f"Top hit: {rs[0].get('title', '')}."
    except Exception as exc:
        return f"Could not look that up: {exc}"
