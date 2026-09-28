"""App manager — list, focus, close, launch Windows apps."""
from __future__ import annotations
import platform
import subprocess
from logger import get_logger

log = get_logger(__name__)
IS_WIN = platform.system() == "Windows"


def list_windows() -> str:
    if not IS_WIN:
        return "[not supported]"
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        windows = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if title:
                windows.append(title)
            return True

        user32.EnumWindows(cb, 0)
        if not windows:
            return "[no visible windows]"
        return "Open windows:\n" + "\n".join(f"  - {w}" for w in windows[:40])
    except Exception as exc:
        return f"[error] {exc}"


def focus_window(name: str) -> str:
    if not IS_WIN:
        return "[not supported]"
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if name.lower() in buf.value.lower():
                found.append((hwnd, buf.value))
                return False
            return True

        user32.EnumWindows(cb, 0)
        if not found:
            return f"[no window matching '{name}']"
        hwnd, title = found[0]
        user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        return f"[ok] focused: {title}"
    except Exception as exc:
        return f"[error] {exc}"


def launch_app(name: str) -> str:
    """Delegate to the universal resolver (no confirm here — the
    mission tier gates this tool before it runs)."""
    try:
        from system import launch as L
        r = L.resolve_app(name or "")
        if r["status"] == "found":
            return "[ok] " + L.launch_target(r["target"])
        if r["status"] == "candidates":
            return "[ask] did you mean: " + ", ".join(r["candidates"])
        return f"[unknown app: {name}]"
    except Exception as exc:
        return f"[error] {exc}"
