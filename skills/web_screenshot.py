from pathlib import Path
from skills.registry import register


@register("web_screenshot", [
    r"^(?:please\s+)?(?:take\s+)?(?:a\s+)?(?:screenshot|capture|screen\s*shot)(?:\s+of\s+(?:this|the)\s+page)?[\?\.\!]?$",
], "Screenshot current page")
def skill(text, match):
    try:
        from skills.browser_agent import get_agent
        d = get_agent().screenshot(full_page=False)
        return f"Screenshot saved to {Path(d['path']).name}."
    except Exception as exc:
        return f"Could not take a screenshot: {exc}"
