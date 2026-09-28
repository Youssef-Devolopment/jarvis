"""Global hotkey — Ctrl+Alt+J brings JARVIS to focus."""
from __future__ import annotations
import webbrowser
from logger import get_logger

log = get_logger(__name__)

_HOTKEY = "ctrl+alt+j"
_URL = "http://127.0.0.1:5000"


def _on_trigger():
    try:
        webbrowser.open(_URL)
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
