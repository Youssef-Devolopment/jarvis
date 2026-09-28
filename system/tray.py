"""System tray icon with context menu."""
from __future__ import annotations
import threading
import webbrowser
from logger import get_logger

log = get_logger(__name__)

_URL = "http://127.0.0.1:5000"


def _make_icon():
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(32, 8), (56, 32), (32, 56), (8, 32)],
              fill=(139, 63, 255, 255), outline=(255, 255, 255, 255))
    d.ellipse([26, 26, 38, 38], fill=(255, 255, 255, 255))
    return img


def start_tray():
    try:
        try:
            from memory import get_pref
            if not get_pref("tray_enabled", True):
                log.info("Tray disabled in prefs")
                return
        except Exception:
            pass

        import pystray
        from pystray import MenuItem as Item, Menu
        import os

        def _open(icon, item):
            webbrowser.open(_URL)

        def _exit(icon, item):
            log.info("Tray: exit requested")
            icon.stop()
            os._exit(0)

        menu = Menu(
            Item("Open JARVIS", _open, default=True),
            Menu.SEPARATOR,
            Item("Exit", _exit),
        )
        icon = pystray.Icon("JARVIS", _make_icon(), "JARVIS", menu)
        log.info("Tray icon starting...")
        icon.run()
    except Exception as exc:
        log.warning("Tray failed: %s", exc)


_icon = None
_thread = None


def _run_launcher_menu():
    """Tray loop wired to the desktop launcher (Open/Restart/Exit)."""
    global _icon
    try:
        import pystray
        from pystray import MenuItem as Item, Menu

        def on_open(icon, item):
            try:
                from system.launcher import open_jarvis_window
                open_jarvis_window()
            except Exception as exc:
                log.warning("Open failed: %s", exc)

        def on_restart(icon, item):
            try:
                from system import notify
                notify.notify("JARVIS",
                              "Exit from the tray, then launch again to restart.")
            except Exception:
                pass
            try:
                from system.launcher import open_jarvis_window
                open_jarvis_window()
            except Exception as exc:
                log.warning("Restart open failed: %s", exc)

        def on_exit(icon, item):
            log.info("Tray: exit requested")
            try:
                from system.launcher import stop_all
                stop_all()
            except Exception:
                pass
            icon.stop()

        menu = Menu(
            Item("Open JARVIS", on_open, default=True),
            Item("Restart", on_restart),
            Menu.SEPARATOR,
            Item("Exit", on_exit),
        )
        _icon = pystray.Icon("JARVIS", _make_icon(), "JARVIS", menu)
        _icon.run()
    except Exception as exc:
        log.warning("Tray (launcher menu) failed: %s", exc)


def start():
    """Start the launcher-wired tray icon in a background thread."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_run_launcher_menu, name="tray",
                               daemon=True)
    _thread.start()


def stop():
    global _icon
    if _icon:
        try:
            _icon.stop()
        except Exception:
            pass
        _icon = None
