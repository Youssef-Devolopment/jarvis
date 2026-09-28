from __future__ import annotations
from threading import Lock
from moods.presets import MOODS, DEFAULT_MOOD
from moods.base import Mood
from logger import get_logger

log = get_logger(__name__)
_lock = Lock()
_current_name = DEFAULT_MOOD


def current() -> Mood:
    with _lock:
        return MOODS[_current_name]


def current_name() -> str:
    with _lock:
        return _current_name


def set_mood(name: str):
    global _current_name
    name = (name or "").lower().strip()
    if name not in MOODS:
        return None
    with _lock:
        _current_name = name
    try:
        from voice.output import apply_mood_voice
        m = MOODS[name]
        apply_mood_voice(rate=m.voice_rate, pitch=m.voice_pitch)
    except Exception:
        pass
    log.info("Mood switched to: %s", name)
    return MOODS[name]


def all_moods() -> list[dict]:
    return [{"name": m.name, "description": m.description} for m in MOODS.values()]


__all__ = ["current", "current_name", "set_mood", "all_moods", "MOODS", "DEFAULT_MOOD"]
