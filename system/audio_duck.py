"""Dynamic audio ducking — lower other apps while JARVIS listens/speaks.

Uses pycaw (Windows session volume, not the global mute keys).
Ref-counted: mic capture and TTS overlap, volumes restore only when
both are done. Our own process sessions are never touched so JARVIS's
voice stays loud. Everything degrades to a no-op when pycaw is missing
or ducking is disabled in prefs.
"""
from __future__ import annotations
import os
import threading
from logger import get_logger

log = get_logger(__name__)

_lock = threading.Lock()
_depth = 0
_saved: dict = {}


def _prefs():
    try:
        from memory import get_pref
        enabled = bool(get_pref("ducking_enabled", True))
        level = float(get_pref("duck_level", 0.25))
    except Exception:
        enabled, level = True, 0.25
    return enabled, max(0.0, min(1.0, level))


def is_available() -> bool:
    if os.name != "nt":
        return False
    try:
        import pycaw  # noqa: F401
        return True
    except ImportError:
        return False


def _sessions():
    """Yield (key, volume_iface) for every non-JARVIS audio session."""
    from pycaw.pycaw import AudioUtilities
    me = os.getpid()
    out = []
    for s in AudioUtilities.GetAllSessions():
        try:
            pid = getattr(s, "ProcessId", None)
            if pid is None:
                proc = getattr(s, "Process", None)
                pid = proc.pid if proc is not None else 0
            if pid == me:
                continue  # never duck our own TTS
            vol = s.SimpleAudioVolume
            try:
                ident = s._ctl.GetSessionInstanceIdentifier()
            except Exception:
                ident = f"pid-{pid}"
            out.append(((pid, str(ident)), vol))
        except Exception:
            continue
    return out


def duck() -> bool:
    """Lower other apps to the pref level. Returns True if ducked."""
    global _depth
    enabled, level = _prefs()
    if not enabled or not is_available():
        return False
    with _lock:
        if _depth == 0:
            _saved.clear()
            try:
                for key, vol in _sessions():
                    try:
                        _saved[key] = float(vol.GetMasterVolume())
                        vol.SetMasterVolume(level, None)
                    except Exception:
                        continue
            except Exception as exc:
                log.debug("Duck enumerate failed: %s", exc)
                return False
            log.info("Ducked %d session(s) to %.0f%%",
                     len(_saved), level * 100)
        _depth += 1
        return True


def restore() -> None:
    """Restore volumes saved by duck(). No-op unless depth hits zero."""
    global _depth
    with _lock:
        if _depth > 0:
            _depth -= 1
        if _depth > 0 or not _saved:
            return
        n = 0
        try:
            current = {k: v for k, v in
                       ((k, vol) for k, vol in _sessions())}
            for key, level in _saved.items():
                vol = current.get(key)
                if vol is None:
                    continue  # session gone, or started after duck
                try:
                    vol.SetMasterVolume(float(level), None)
                    n += 1
                except Exception:
                    continue
        except Exception as exc:
            log.debug("Restore enumerate failed: %s", exc)
        finally:
            _saved.clear()
        log.info("Restored %d session(s)", n)


class ducked:
    """Context manager: `with ducked(): ...`"""
    def __enter__(self):
        duck()
        return self

    def __exit__(self, *a):
        restore()
        return False
