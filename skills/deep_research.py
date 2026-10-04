"""Deep-research a topic: search, fetch, report to docs/research/."""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

RESEARCH_PATTERNS = [
    r"^(?:deep\s+)?research\s+(?P<topic>.+?)[\?\.\!]?$",
    r"^investigate\s+(?P<topic>.+?)[\?\.\!]?$",
]


@register("deep_research", RESEARCH_PATTERNS,
          "Deep-research a topic into docs/research/")
def skill_research(text, m):
    topic = ((m.group("topic") if "topic" in m.groupdict() else "") or "").strip()
    if not topic:
        return None
    try:
        from system import research_agent as ra
        res = ra.research_topic(topic)
    except Exception as exc:
        log.warning("research skill failed: %s", exc)
        return "Research failed before it started."
    if not res.get("ok"):
        return f"Research failed: {res.get('error', 'unknown error')}"
    tldr = (res.get("tldr") or "")[:600]
    return f"Report saved: {res['path']}\n\n{tldr}"
