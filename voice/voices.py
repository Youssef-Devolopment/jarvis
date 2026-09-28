"""British voices."""
from __future__ import annotations

VOICES = {
    "oliver": {"id": "en-GB-OliverNeural", "label": "Oliver",
               "desc": "Deep, calm, butler-like", "rate": "-8%", "pitch": "-3Hz"},
    "ryan":   {"id": "en-GB-RyanNeural", "label": "Ryan",
               "desc": "Warm, classic British male", "rate": "-5%", "pitch": "-2Hz"},
    "thomas": {"id": "en-GB-ThomasNeural", "label": "Thomas",
               "desc": "Older, authoritative", "rate": "-3%", "pitch": "-4Hz"},
    "sonia":  {"id": "en-GB-SoniaNeural", "label": "Sonia",
               "desc": "Clear, professional female", "rate": "-3%", "pitch": "+0Hz"},
    "libby":  {"id": "en-GB-LibbyNeural", "label": "Libby",
               "desc": "Younger female", "rate": "+0%", "pitch": "+0Hz"},
}
DEFAULT_VOICE = "oliver"


def get_voice(key: str):
    return VOICES.get((key or "").lower())


def all_voices():
    return [{"key": k, **v} for k, v in VOICES.items()]
