"""Desktop keyboard control via pyautogui. Gated by Code Mode."""
from __future__ import annotations
import time
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _pg():
    try:
        import pyautogui
        pyautogui.FAILSAFE = True   # mouse to top-left corner = abort
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


@register("desktop_type", [
    r"^type\s+this[:]?\s+(?P<text>.+?)[\?\.\!]?$",
    r"^type\s+text[:]?\s+(?P<text2>.+?)[\?\.\!]?$",
], "Type text into the focused window")
def s_type(text, m):
    if not _gated():
        return "OVERRIDE is locked. Enable Code Mode to allow typing."
    gd = m.groupdict()
    txt = (gd.get("text") or gd.get("text2") or "").strip()
    if not txt:
        return None
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    try:
        pg.typewrite(txt, interval=0.015)
        return f"Typed: {txt[:60]}"
    except Exception as exc:
        return f"Typing failed: {str(exc)[:80]}"


@register("desktop_press", [
    r"^press\s+(?:the\s+)?key\s+(?P<key1>[\w\+\-]+)[\?\.\!]?$",
    r"^press\s+(?P<key2>enter|tab|escape|esc|space|backspace|delete|"
    r"up|down|left|right|home|end|pageup|pagedown|f\d{1,2})[\?\.\!]?$",
], "Press a keyboard key")
def s_press(text, m):
    if not _gated():
        return "OVERRIDE is locked."
    gd = m.groupdict()
    key = (gd.get("key1") or gd.get("key2") or "").strip().lower()
    if not key:
        return None
    keymap = {"esc": "escape", "pageup": "pageup", "pagedown": "pagedown"}
    key = keymap.get(key, key)
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    try:
        pg.press(key)
        return f"Pressed {key}."
    except Exception as exc:
        return f"Press failed: {str(exc)[:80]}"


@register("desktop_hotkey", [
    r"^(?:press|hit)\s+(?:the\s+)?(?:shortcut|hotkey|combo)\s+(?P<combo>[\w\+\-]+)[\?\.\!]?$",
    r"^(?P<name>copy|paste|cut|undo|redo|save|select all|"
    r"close window|switch window|new tab|close tab|reopen tab|"
    r"refresh|find|minimize all)[\?\.\!]?$",
], "Press a keyboard shortcut")
def s_hotkey(text, m):
    if not _gated():
        return "OVERRIDE is locked."
    gd = m.groupdict()
    combo = (gd.get("combo") or "").strip().lower()
    name = (gd.get("name") or "").strip().lower()
    if not combo and name:
        mapping = {
            "copy": "ctrl+c", "paste": "ctrl+v", "cut": "ctrl+x",
            "undo": "ctrl+z", "redo": "ctrl+y", "save": "ctrl+s",
            "select all": "ctrl+a", "close window": "alt+f4",
            "switch window": "alt+tab", "new tab": "ctrl+t",
            "close tab": "ctrl+w", "reopen tab": "ctrl+shift+t",
            "refresh": "f5", "find": "ctrl+f",
            "minimize all": "win+d",
        }
        combo = mapping.get(name, "")
    if not combo:
        return None
    pg = _pg()
    if not pg:
        return "pyautogui not installed."
    try:
        keys = [k.strip() for k in combo.replace("+", " ").split()]
        pg.hotkey(*keys)
        return f"Pressed {'+'.join(keys)}."
    except Exception as exc:
        return f"Hotkey failed: {str(exc)[:80]}"
