"""System control skills: volume, brightness, lock, screenshot."""
from __future__ import annotations
import platform
import subprocess
import time
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)
IS_WIN = platform.system() == "Windows"

_SHOT_DIR = Path(__file__).resolve().parent.parent / "logs" / "screenshots"
_SHOT_DIR.mkdir(parents=True, exist_ok=True)


def _press(key: str, times: int = 1):
    try:
        import pyautogui
        for _ in range(times):
            pyautogui.press(key)
        return True
    except Exception as exc:
        log.warning("pyautogui press failed: %s", exc)
        return False


def _volume_up():
    if _press("volumeup", 3):
        return "Volume up."
    return "Volume control unavailable."


def _volume_down():
    if _press("volumedown", 3):
        return "Volume down."
    return "Volume control unavailable."


def _volume_mute():
    if _press("volumemute", 1):
        return "Muted."
    return "Mute unavailable."


def _brightness(delta: int):
    """Use PowerShell WMI — reliable on Windows 10/11."""
    if not IS_WIN:
        return "Brightness only on Windows."
    try:
        # Get current brightness
        ps_get = ('powershell -NoProfile -Command "'
                  '(Get-WmiObject -Namespace root/WMI '
                  '-Class WmiMonitorBrightness).CurrentBrightness"')
        cur_raw = subprocess.run(ps_get, capture_output=True, text=True, timeout=5)
        cur = int(cur_raw.stdout.strip() or "50")
        new = max(0, min(100, cur + delta))
        ps_set = ('powershell -NoProfile -Command "'
                  f'(Get-WmiObject -Namespace root/WMI '
                  f'-Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{new})"')
        subprocess.run(ps_set, capture_output=True, timeout=5)
        return f"Brightness {new} percent."
    except Exception as exc:
        return f"Brightness failed: {str(exc)[:60]}"


def _lock():
    if not IS_WIN:
        return "Lock only on Windows."
    try:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return "Locking the screen."
    except Exception as exc:
        return f"Lock failed: {exc}"


def _screenshot():
    try:
        import pyautogui
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = _SHOT_DIR / f"screen_{ts}.png"
        pyautogui.screenshot(str(path))
        return f"Screenshot saved as {path.name}."
    except Exception as exc:
        return f"Screenshot failed: {str(exc)[:60]}"


@register("volume_up", [
    r"\b(?:turn\s+)?(?:the\s+)?volume\s+(?:up|higher)\b",
    r"\b(?:louder|increase\s+volume|raise\s+volume|volume\s+up)\b",
], "Volume up")
def s_vol_up(text, m): return _volume_up()


@register("volume_down", [
    r"\b(?:turn\s+)?(?:the\s+)?volume\s+(?:down|lower)\b",
    r"\b(?:quieter|decrease\s+volume|lower\s+volume|volume\s+down)\b",
], "Volume down")
def s_vol_down(text, m): return _volume_down()


@register("volume_mute", [
    r"\b(?:mute|unmute)\b",
    r"^(?:shut\s+up|silence)[\?\.\!]?$",
], "Mute / unmute")
def s_mute(text, m): return _volume_mute()


@register("brightness_up", [
    r"\b(?:brightness|screen)\s+(?:up|higher|brighter)\b",
    r"^(?:brighter|increase\s+brightness)[\?\.\!]?$",
], "Brightness up")
def s_bright_up(text, m): return _brightness(10)


@register("brightness_down", [
    r"\b(?:brightness|screen)\s+(?:down|lower|dimmer)\b",
    r"^(?:dimmer|decrease\s+brightness|lower\s+brightness)[\?\.\!]?$",
], "Brightness down")
def s_bright_down(text, m): return _brightness(-10)


@register("lock_pc", [
    r"\b(?:lock|secure)\s+(?:the\s+)?(?:screen|pc|computer|windows)\b",
    r"^(?:lock\s+it|lock\s+screen)[\?\.\!]?$",
], "Lock screen")
def s_lock(text, m): return _lock()


@register("screenshot", [
    r"^(?:take\s+)?(?:a\s+)?screenshot(?:\s+of\s+(?:the\s+)?screen)?[\?\.\!]?$",
    r"^capture\s+(?:the\s+)?screen[\?\.\!]?$",
], "Take screenshot")
def s_screenshot(text, m): return _screenshot()


@register("volume_set", [
    r"\b(?:set\s+)?volume\s+(?:to\s+)?(?P<level>\d{1,3})\b",
], "Set volume to a specific level (0-100)")
def s_volume_set(text, m):
    level = max(0, min(100, int(m.group("level"))))
    # pyautogui approach — press up/down until level reached is
    # unreliable, so use pycaw if available else nudge
    try:
        from ctypes import cast, POINTER
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
        devices = AudioUtilities.GetSpeakers()
        interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        vol = cast(interface, POINTER(IAudioEndpointVolume))
        vol.SetMasterVolumeLevelScalar(level / 100.0, None)
        return f"Volume set to {level}%."
    except Exception:
        return f"Cannot set exact volume. Try 'volume up' or 'volume down'."


@register("brightness_set", [
    r"\b(?:set\s+)?brightness\s+(?:to\s+)?(?P<level>\d{1,3})\b",
], "Set brightness to a specific level (0-100)")
def s_brightness_set(text, m):
    level = max(0, min(100, int(m.group("level"))))
    try:
        import subprocess
        ps = ('powershell -NoProfile -Command "'
              f'(Get-WmiObject -Namespace root/WMI '
              f'-Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"')
        subprocess.run(ps, capture_output=True, timeout=5)
        return f"Brightness set to {level}%."
    except Exception as exc:
        return f"Brightness set failed: {str(exc)[:60]}"