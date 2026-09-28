"""Natural-language cross-app bridge skill."""

from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


@register("bridge_transfer", [
    r"^(?:take|copy|move|send|transfer|get)\s+"
    r"(?:the\s+)?(?P<what>[\w\s]+?)\s+"
    r"(?:from|in)\s+(?P<source>[\w\s]+?)\s+"
    r"(?:to|into)\s+(?P<target>[\w\s]+?)[\?\.\!]?$",
], "Transfer content between apps")
def skill_bridge(text, match):
    source = match.group("source").strip()
    target = match.group("target").strip()
    what = (match.group("what") or "").strip().lower()

    action = "copy"
    if "link" in what or "url" in what:
        action = "link"

    try:
        from ai import bridge
        result = bridge.transfer(source, target, action)
        return result
    except Exception as exc:
        return f"Bridge failed: {str(exc)[:120]}"
