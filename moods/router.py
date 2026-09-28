"""Router — decides between JARVIS fast skills and OpenHands heavy tasks."""
from __future__ import annotations
import re

FAST_MODEL = "qwen3.8-flash:free"
REASON_MODEL = "deepseek-v4.1-flash:free"

HEAVY_PATTERNS = [
    r"\bbook\s+(?:a|the)\b",
    r"\breserve\s+(?:a|the)\b",
    r"\border\s+(?:a|the)\s+\w+\s+(?:from|on)\b",
    r"\bbuy\s+(?:a|the)\b",
    r"\bcheckout\b",
    r"\bfill\s+(?:in|out)\s+(?:the\s+)?form\b",
    r"\bcompare\s+(?:prices?|options?)\s+(?:across|on|between)\b",
    r"\bautomate\b",
    r"\bscrape\b",
    r"\bmulti[-\s]?step\b",
]

SIMPLE_PATTERNS = [
    r"\bwhat\s+time\b",
    r"\bwhat\s+(?:day|date)\b",
    r"\bweather\b",
    r"\bconvert\s+\d",
    r"^\d+[\s\+\-\*/]",
    r"\bdefine\s+\w+\b",
    r"\btranslate\b",
    r"\bquote\b",
    r"\bnote\b",
    r"\btodo\b",
    r"\btimer\b",
    r"\bremind\s+me\b",
]

_HEAVY = [re.compile(p, re.IGNORECASE) for p in HEAVY_PATTERNS]
_SIMPLE = [re.compile(p, re.IGNORECASE) for p in SIMPLE_PATTERNS]


def _matches(patterns, text):
    return any(p.search(text) for p in patterns)


def needs_reasoning(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if len(t) > 300:
        return True
    if t.count("?") >= 3:
        return True
    return False


def is_heavy_task(text: str) -> bool:
    if not text:
        return False
    t = text.strip()
    if re.search(r"\b(?:use\s+openhands|let\s+openhands|delegate)\b",
                 t, re.IGNORECASE):
        return True
    if _matches(_SIMPLE, t):
        return False
    return _matches(_HEAVY, t)


def pick_model(text, *, manual_override="", mood_reasoner=False,
               mood_fastest=False):
    if manual_override and manual_override != "auto":
        return manual_override
    if mood_fastest:
        return FAST_MODEL
    if mood_reasoner or needs_reasoning(text):
        return REASON_MODEL
    return FAST_MODEL
