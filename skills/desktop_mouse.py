"""Desktop mouse control via pyautogui. Gated by Code Mode."""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _pg():
    try:
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.02
        return pyautogui
    except ImportError:
        return None


def _gated():
    try:
        from memory import get_pref
        return bool(get_pref("code_mode_enabled", False))
    except Exception:
        return False


@register("desktop_move", [
    r"^move\s+(?:the\s+)?mouse\s+(?P<dir>up|down|left|right)"
    r"(?:\s+(?P<amount>\d+))?[\?\.\!]?$",
], "Move the mouse")
def s_move(text, m):
    if not _gated():
        return "OVERRIDE is locked."
    direction = m.group("dir").lower()
    amount = int(m.group("amount") or 200)
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    try:
        x, y = pg.position()
        dx = dy = 0
        if direction == "up":    dy = -amount
        elif direction == "down":  dy = amount
        elif direction == "left":  dx = -amount
        elif direction == "right": dx = amount
        pg.moveTo(x + dx, y + dy, duration=0.25)
        return f"Moved {direction} {amount}px."
    except Exception as exc:
        return f"Move failed: {str(exc)[:80]}"


@register("desktop_click", [
    r"^click[\?\.\!]?$",
    r"^left\s*click[\?\.\!]?$",
    r"^right\s*click[\?\.\!]?$",
    r"^double\s*click[\?\.\!]?$",
    r"^middle\s*click[\?\.\!]?$",
], "Click the mouse")
def s_click(text, m):
    if not _gated():
        return "OVERRIDE is locked."
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    low = text.lower().strip(" ?.!")
    try:
        if "right" in low:
            pg.click(button="right");  return "Right-clicked."
        if "double" in low:
            pg.doubleClick();          return "Double-clicked."
        if "middle" in low:
            pg.click(button="middle"); return "Middle-clicked."
        pg.click();                    return "Clicked."
    except Exception as exc:
        return f"Click failed: {str(exc)[:80]}"


@register("desktop_drag", [
    r"^drag\s+(?:mouse\s+)?(?P<dx>-?\d+)\s+(?P<dy>-?\d+)[\?\.\!]?$",
], "Drag the mouse")
def s_drag(text, m):
    if not _gated():
        return "OVERRIDE is locked."
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    try:
        dx = int(m.group("dx"))
        dy = int(m.group("dy"))
        x, y = pg.position()
        pg.dragTo(x + dx, y + dy, duration=0.4, button="left")
        return f"Dragged {dx},{dy}."
    except Exception as exc:
        return f"Drag failed: {str(exc)[:80]}"


@register("desktop_scroll", [
    r"^scroll\s+(?P<dir>up|down)(?:\s+(?P<amount>\d+))?[\?\.\!]?$",
], "Scroll the mouse wheel")
def s_scroll(text, m):
    if not _gated():
        return "OVERRIDE is locked."
    direction = m.group("dir").lower()
    amount = int(m.group("amount") or 3)
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    try:
        clicks = amount if direction == "up" else -amount
        pg.scroll(clicks)
        return f"Scrolled {direction}."
    except Exception as exc:
        return f"Scroll failed: {str(exc)[:80]}"


@register("desktop_position", [
    r"^where(?:'s|\s+is)\s+the\s+mouse[\?\.\!]?$",
    r"^mouse\s+position[\?\.\!]?$",
], "Get mouse position")
def s_position(text, m):
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    try:
        x, y = pg.position()
        size = pg.size()
        return f"Mouse at ({x}, {y}) on a {size.width}x{size.height} screen."
    except Exception as exc:
        return f"Position failed: {str(exc)[:80]}"


@register("desktop_screen_size", [
    r"^screen\s+size[\?\.\!]?$",
], "Get screen size")
def s_size(text, m):
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    try:
        size = pg.size()
        return f"Screen is {size.width}x{size.height}."
    except Exception as exc:
        return f"Size failed: {str(exc)[:80]}"
