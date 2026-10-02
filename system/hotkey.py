"""Global hotkeys — Ctrl+Alt+J opens JARVIS, Alt+Space shows the overlay."""
from __future__ import annotations
import webbrowser
from logger import get_logger

log = get_logger(__name__)

_HOTKEY = "ctrl+alt+j"


def _on_trigger():
    try:
        from config import get_settings
        s = get_settings()
        import webbrowser
        webbrowser.open(f"http://{s.host}:{s.port}")
        log.info("Hotkey %s triggered", _HOTKEY)
    except Exception as exc:
        log.warning("Hotkey action failed: %s", exc)


def start_hotkey_listener():
    try:
        try:
            from memory import get_pref
            if not get_pref("hotkey_enabled", True):
                log.info("Hotkey disabled in prefs")
                return
        except Exception:
            pass

        try:
            import keyboard
            keyboard.add_hotkey(_HOTKEY, _on_trigger, suppress=False)
            log.info("Hotkey registered: %s (via keyboard)", _HOTKEY)
            keyboard.wait()
        except ImportError:
            from pynput import keyboard as pk
            current = set()

            def on_press(key):
                current.add(key)
                if hasattr(key, 'char') and key.char == 'j':
                    if pk.Key.ctrl_l in current and pk.Key.alt_l in current:
                        _on_trigger()

            def on_release(key):
                try:
                    current.discard(key)
                except Exception:
                    pass

            listener = pk.Listener(on_press=on_press, on_release=on_release)
            listener.start()
            log.info("Hotkey registered: %s (via pynput)", _HOTKEY)
            listener.join()
    except Exception as exc:
        log.warning("Hotkey listener failed: %s", exc)


def start_open_jarvis():
    """Register Ctrl+Alt+J to open the JARVIS window (non-blocking).

    Kept separate from start_hotkey_listener() (used by run.py) so the
    desktop launcher gets a non-blocking registration that routes
    through system.launcher.open_jarvis_window().
    """
    try:
        try:
            from memory import get_pref
            if not get_pref("hotkey_enabled", True):
                log.info("Hotkey disabled in prefs")
                return
        except Exception:
            pass

        try:
            from system.launcher import open_jarvis_window as _open
        except Exception:
            _open = _on_trigger  # launcher unavailable: open URL directly

        try:
            import keyboard
            keyboard.add_hotkey(_HOTKEY, _open, suppress=False)
            log.info("Hotkey registered: %s (via keyboard)", _HOTKEY)
            return
        except ImportError:
            pass
        from pynput import keyboard as pk
        current = set()

        def on_press(key):
            current.add(key)
            if hasattr(key, 'char') and key.char == 'j':
                if pk.Key.ctrl_l in current and pk.Key.alt_l in current:
                    _open()

        def on_release(key):
            try:
                current.discard(key)
            except Exception:
                pass

        listener = pk.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()
        log.info("Hotkey registered: %s (via pynput)", _HOTKEY)
    except Exception as exc:
        log.warning("Hotkey setup failed: %s", exc)


def start_overlay_hotkey():
    """Register Alt+Space -> floating HUD overlay (non-blocking)."""
    try:
        try:
            from memory import get_pref
            if not get_pref("overlay_enabled", True):
                log.info("Overlay hotkey disabled in prefs")
                return
        except Exception:
            pass

        def _fire():
            from system import overlay
            overlay.toggle()

        try:
            import keyboard
            keyboard.add_hotkey("alt+space", _fire, suppress=False)
            log.info("Hotkey registered: alt+space -> overlay (keyboard)")
            return
        except ImportError:
            pass
        from pynput import keyboard as pk
        current = set()

        def on_press(key):
            current.add(key)
            if key == pk.Key.space and pk.Key.alt_l in current:
                _fire()

        def on_release(key):
            try:
                current.discard(key)
            except Exception:
                pass

        listener = pk.Listener(on_press=on_press, on_release=on_release)
        listener.daemon = True
        listener.start()
        log.info("Hotkey registered: alt+space -> overlay (pynput)")
    except Exception as exc:
        log.warning("Overlay hotkey setup failed: %s", exc)


def start():
    start_open_jarvis()
    start_overlay_hotkey()
