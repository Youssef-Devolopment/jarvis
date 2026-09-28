"""Cross-app bridge — move content between applications via clipboard."""

from __future__ import annotations
import platform
import re
import time
from typing import Optional
from logger import get_logger

log = get_logger(__name__)

IS_WIN = platform.system() == "Windows"

# Known app aliases → window title substrings
APP_ALIASES = {
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "chrome": "Chrome",
    "brave": "Brave",
    "edge": "Edge",
    "firefox": "Firefox",
    "discord": "Discord",
    "slack": "Slack",
    "telegram": "Telegram",
    "whatsapp": "WhatsApp",
    "notion": "Notion",
    "obsidian": "Obsidian",
    "word": "Word",
    "excel": "Excel",
    "powerpoint": "PowerPoint",
    "outlook": "Outlook",
    "gmail": "Gmail",
    "terminal": "Terminal",
    "powershell": "PowerShell",
    "cmd": "Command Prompt",
    "notepad": "Notepad",
    "browser": "Chrome",
    "chatgpt": "ChatGPT",
}


def _clipboard_get() -> str:
    try:
        import pyperclip
        return pyperclip.paste() or ""
    except ImportError:
        try:
            import tkinter
            r = tkinter.Tk()
            r.withdraw()
            txt = r.clipboard_get()
            r.destroy()
            return txt or ""
        except Exception:
            return ""


def _clipboard_set(text: str) -> bool:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True
    except ImportError:
        try:
            import tkinter
            r = tkinter.Tk()
            r.withdraw()
            r.clipboard_clear()
            r.clipboard_append(text)
            r.update()
            r.destroy()
            return True
        except Exception:
            return False


def _find_and_focus(app_name: str) -> bool:
    """Find a window whose title contains app_name and focus it."""
    if not IS_WIN:
        return False
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        target = APP_ALIASES.get(app_name.lower(), app_name)
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
            title = buf.value
            if target.lower() in title.lower():
                found.append((hwnd, title))
                return False
            return True

        user32.EnumWindows(cb, 0)
        if not found:
            return False
        hwnd, title = found[0]
        user32.ShowWindow(hwnd, 9)      # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.4)
        return True
    except Exception as exc:
        log.warning("Focus failed for %s: %s", app_name, exc)
        return False


def _paste_into_focused():
    """Send Ctrl+V to the currently focused window."""
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
        return True
    except Exception as exc:
        log.warning("Paste failed: %s", exc)
        return False


def _copy_from_focused():
    """Send Ctrl+C to the currently focused window."""
    try:
        import pyautogui
        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.3)
        return True
    except Exception as exc:
        log.warning("Copy failed: %s", exc)
        return False


def _launch_if_needed(app_name: str) -> bool:
    """Try to launch the app if it's not open."""
    try:
        from ai import app_manager
        result = app_manager.launch_app(app_name)
        if "[ok]" in result:
            time.sleep(2.5)
            return True
        return False
    except Exception:
        return False


def transfer(source: str, target: str, action: str = "copy") -> str:
    """Transfer content between two apps.

    action:
      "copy"  — Ctrl+C in source, focus target, Ctrl+V
      "paste" — alias for copy
      "link"  — same as copy (browser uses Ctrl+L to copy URL if source=chrome)
    """
    source = (source or "").strip()
    target = (target or "").strip()
    if not source or not target:
        return "[error] missing source or target"

    log.info("Bridge: %s → %s (%s)", source, target, action)

    # Step 1: focus source
    if not _find_and_focus(source):
        log.info("Source %s not open — trying to launch", source)
        if not _launch_if_needed(source):
            return f"[error] could not find or launch '{source}'"

    # Step 2: copy from source
    # Special case: Chrome/Brave URL — use Ctrl+L to select address bar
    source_low = source.lower()
    if action == "link" or "url" in action.lower():
        if any(x in source_low for x in ("chrome", "brave", "edge", "firefox", "browser")):
            try:
                import pyautogui
                pyautogui.hotkey("ctrl", "l")
                time.sleep(0.3)
                pyautogui.hotkey("ctrl", "c")
                time.sleep(0.3)
            except Exception as exc:
                return f"[error] could not copy URL: {exc}"
        else:
            _copy_from_focused()
    else:
        _copy_from_focused()

    time.sleep(0.3)

    # Verify clipboard has content
    content = _clipboard_get()
    if not content or len(content) < 2:
        return f"[error] nothing was copied from {source}"

    preview = content[:80].replace("\n", " ")

    # Step 3: focus target
    if not _find_and_focus(target):
        log.info("Target %s not open — trying to launch", target)
        if not _launch_if_needed(target):
            # Restore source focus so at least user sees what happened
            _find_and_focus(source)
            return f"[error] could not find or launch '{target}'"

    time.sleep(0.5)

    # Step 4: paste
    if not _paste_into_focused():
        return f"[error] paste into {target} failed"

    return (f"[ok] transferred {len(content)} chars "
            f"from {source} to {target} "
            f"(preview: {preview}...)")
