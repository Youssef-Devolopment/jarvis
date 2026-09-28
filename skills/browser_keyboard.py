"""Browser keyboard control: type, press keys, tab management, scroll."""
from __future__ import annotations
import time
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _get_page():
    from skills.browser_agent import get_agent
    agent = get_agent()
    agent._ensure_started()
    # Access the page via a new method
    return agent


@register("browser_type", [
    r"^(?:type|write)\s+[\"']?(?P<text>.+?)[\"']?(?:\s+in\s+(?:the\s+)?(?:search|field|box|input))?[\?\.\!]?$",
], "Type text into the page")
def skill_type(text, m):
    txt = (m.group("text") or "").strip()
    if not txt:
        return None
    try:
        from skills.browser_agent import get_agent
        get_agent().type_text(txt)
        return f"Typed: {txt[:60]}"
    except Exception as exc:
        return f"Could not type: {exc}"


@register("browser_press", [
    r"^(?:press|hit)\s+(?:the\s+)?(?P<key>enter|tab|escape|esc|space|backspace|"
    r"delete|up|down|left|right|home|end|page\s*up|page\s*down)[\?\.\!]?$",
], "Press a key")
def skill_press(text, m):
    key = (m.group("key") or "").strip().lower().replace(" ", "")
    keymap = {"esc": "Escape", "space": " "}
    key = keymap.get(key, key.capitalize() if len(key) > 1 else key)
    try:
        from skills.browser_agent import get_agent
        get_agent().press_key(key)
        return f"Pressed {key}."
    except Exception as exc:
        return f"Could not press {key}: {exc}"


@register("browser_scroll", [
    r"^scroll\s+(?P<dir>up|down|top|bottom)(?:\s+(?P<amount>\d+))?[\?\.\!]?$",
], "Scroll the page")
def skill_scroll(text, m):
    direction = m.group("dir").lower()
    try:
        from skills.browser_agent import get_agent
        get_agent().scroll(direction)
        return f"Scrolled {direction}."
    except Exception as exc:
        return f"Could not scroll: {exc}"


@register("browser_new_tab", [
    r"^(?:open\s+)?(?:a\s+)?new\s+tab[\?\.\!]?$",
], "New browser tab")
def skill_new_tab(text, m):
    try:
        from skills.browser_agent import get_agent
        get_agent().new_tab()
        return "Opened a new tab."
    except Exception as exc:
        return f"Could not open tab: {exc}"


@register("browser_close_tab", [
    r"^close\s+(?:the\s+)?tab[\?\.\!]?$",
], "Close current tab")
def skill_close_tab(text, m):
    try:
        from skills.browser_agent import get_agent
        get_agent().close_tab()
        return "Closed the tab."
    except Exception as exc:
        return f"Could not close tab: {exc}"


@register("browser_back", [
    r"^go\s+back[\?\.\!]?$", r"^(?:browser\s+)?back[\?\.\!]?$",
], "Go back in browser")
def skill_back(text, m):
    try:
        from skills.browser_agent import get_agent
        get_agent().back()
        return "Went back."
    except Exception as exc:
        return f"Could not go back: {exc}"


@register("browser_forward", [
    r"^go\s+forward[\?\.\!]?$",
], "Go forward in browser")
def skill_forward(text, m):
    try:
        from skills.browser_agent import get_agent
        get_agent().forward()
        return "Went forward."
    except Exception as exc:
        return f"Could not go forward: {exc}"


@register("browser_refresh", [
    r"^(?:refresh|reload)(?:\s+the\s+page)?[\?\.\!]?$",
], "Reload page")
def skill_refresh(text, m):
    try:
        from skills.browser_agent import get_agent
        get_agent().reload()
        return "Reloaded the page."
    except Exception as exc:
        return f"Could not reload: {exc}"
