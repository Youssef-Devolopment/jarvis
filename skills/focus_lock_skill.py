"""Focus lock skill."""
import re
from skills.registry import register

@register("focus_lock", [
    r"^(?:focus|deep\s+work)\s+(?:for\s+)?(?P<mins>\d+)\s*(?:minutes?|mins?|m)[\?\.\!]?$",
    r"^focus\s+mode[\?\.\!]?$",
    r"^stop\s+focus[\?\.\!]?$",
], "Focus lock — block distractions")
def skill_focus(text, match):
    try:
        from ai import focus_lock
        if "stop" in text.lower():
            focus_lock.stop()
            return "Focus mode off."
        m = match.groupdict().get("mins")
        mins = int(m) if m else 60
        ok = focus_lock.start(mins)
        return f"Focus mode ON for {mins} min. I'll block distractions." if ok else "Focus already active."
    except Exception as exc:
        return f"Focus failed: {str(exc)[:100]}"
