"""Personality system — formality, humor, verbosity sliders."""
from __future__ import annotations
from dataclasses import dataclass
from threading import Lock
from logger import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Personality:
    name: str
    formality: int   # 0 casual ... 100 formal
    humor: int       # 0 dry ... 100 playful
    verbosity: int   # 0 brief ... 100 detailed

    def system_suffix(self) -> str:
        parts = []
        # Formality
        if self.formality >= 75:
            parts.append("Address the user as 'sir'. Use formal phrasing.")
        elif self.formality <= 25:
            parts.append("Speak casually, like a friend. First names are fine.")
        else:
            parts.append("Be polite but relaxed.")
        # Humor
        if self.humor >= 75:
            parts.append("Add light wit or a playful remark when natural.")
        elif self.humor <= 25:
            parts.append("Stay straight and factual. No jokes.")
        # Verbosity
        if self.verbosity >= 75:
            parts.append("Give thorough answers, add useful context.")
        elif self.verbosity <= 25:
            parts.append("Be extremely brief. One short sentence if possible.")
        else:
            parts.append("Keep answers concise.")
        return " ".join(parts)

    def voice_rate(self) -> str:
        # Slow down for formal, speed up for casual
        if self.formality >= 75: return "-8%"
        if self.formality <= 25: return "+4%"
        return "-3%"

    def voice_pitch(self) -> str:
        if self.formality >= 75: return "-3Hz"
        return "-2Hz"


PRESETS: dict[str, Personality] = {
    "butler": Personality("Butler", 85, 40, 50),
    "friend": Personality("Friend", 25, 75, 30),
    "tutor":  Personality("Tutor",  70, 20, 85),
    "default": Personality("Default", 50, 50, 50),
}

_lock = Lock()
_current = PRESETS["default"]


def current() -> Personality:
    with _lock:
        return _current


def current_name() -> str:
    with _lock:
        return _current.name.lower()


def set_preset(name: str) -> Personality | None:
    global _current
    key = (name or "").lower().strip()
    if key not in PRESETS:
        return None
    with _lock:
        _current = PRESETS[key]
    try:
        from voice.output import apply_mood_voice
        apply_mood_voice(rate=_current.voice_rate(), pitch=_current.voice_pitch())
    except Exception:
        pass
    log.info("Personality preset: %s", key)
    return _current


def set_values(formality: int, humor: int, verbosity: int) -> Personality:
    global _current
    f = max(0, min(100, int(formality)))
    h = max(0, min(100, int(humor)))
    v = max(0, min(100, int(verbosity)))
    with _lock:
        _current = Personality("Custom", f, h, v)
    try:
        from voice.output import apply_mood_voice
        apply_mood_voice(rate=_current.voice_rate(), pitch=_current.voice_pitch())
    except Exception:
        pass
    log.info("Personality custom: f=%d h=%d v=%d", f, h, v)
    return _current


def all_presets() -> list[dict]:
    return [
        {"name": k, "formality": p.formality,
         "humor": p.humor, "verbosity": p.verbosity}
        for k, p in PRESETS.items()
    ]


def current_dict() -> dict:
    c = current()
    return {
        "name": c.name.lower(),
        "formality": c.formality,
        "humor": c.humor,
        "verbosity": c.verbosity,
    }
