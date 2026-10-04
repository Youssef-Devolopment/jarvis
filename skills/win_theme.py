"""Deep Windows appearance control: dark/light mode + transparency.

HKCU-only (no elevation), broadcast applied instantly. No confirm
gate: every action is one click reversible in Settings.
"""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

WIN_THEME_PATTERNS = [
    r"^(?:switch\s+to|turn\s+on|enable|use)\s+(?:windows\s+)?dark\s+mode[\?\.\!]?$",
    r"^(?:switch\s+to|turn\s+on|enable|use)\s+(?:windows\s+)?light\s+mode[\?\.\!]?$",
    r"^(?:turn\s+off|disable)\s+(?:windows\s+)?dark\s+mode[\?\.\!]?$",
    r"^(?:turn\s+)?(?:on|off)\s+transparency(?:\s+effects?)?[\?\.\!]?$",
]

_PERSONALIZE = (r"Software\Microsoft\Windows\CurrentVersion"
                r"\Themes\Personalize")


def _set_dword(name: str, value: int) -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE,
                            0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)
        _broadcast()
        return True
    except Exception as exc:
        log.warning("theme write failed: %s", exc)
        return False


def _get_dword(name: str, default: int = 1) -> int:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE,
                            0, winreg.KEY_READ) as k:
            val, _ = winreg.QueryValueEx(k, name)
            return int(val)
    except Exception:
        return default


def _broadcast() -> None:
    """Tell Explorer/settings to re-read the theme now."""
    try:
        import ctypes
        HWND_BROADCAST, WM_SETTINGCHANGE = 0xFFFF, 0x001A
        ctypes.windll.user32.SendMessageTimeoutW(
            HWND_BROADCAST, WM_SETTINGCHANGE, 0,
            "ImmersiveColorSet", 0x0002, 5000, None)
    except Exception:
        pass


def _apply(text: str) -> str:
    t = (text or "").lower().strip().rstrip("?.!")
    if "transparency" in t:
        want_on = not (t.startswith("turn off")
                       or t.startswith("disable"))
        if not _set_dword("EnableTransparency", 1 if want_on else 0):
            return "Could not change transparency."
        return ("Transparency effects on." if want_on
                else "Transparency effects off.")
    if "light" in t and "dark" not in t.split():
        dark = False
    elif t.startswith("turn off") or t.startswith("disable"):
        dark = False
    else:
        dark = True
    ok = (_set_dword("AppsUseLightTheme", 0 if dark else 1)
          and _set_dword("SystemUsesLightTheme", 0 if dark else 1))
    if not ok:
        return "Could not change the theme."
    return "Dark mode on." if dark else "Light mode on."


@register("win_theme", WIN_THEME_PATTERNS, "Windows dark/light/transparency")
def skill_win_theme(text, m):
    try:
        return _apply(text)
    except Exception as exc:
        log.warning("win theme failed: %s", exc)
        return "Could not change the theme."
