"""System tray icon with context menu."""
from __future__ import annotations
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
