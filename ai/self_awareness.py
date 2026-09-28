"""Self-awareness — detect conversational vs task-oriented input."""
from __future__ import annotations
import re

# Patterns that indicate purely conversational / chitchat input
_CONV_PATTERNS = [
    r"^\b(?:hi|hello|hey|sup|yo|hiya|howdy)\b",
    r"^\bhow(?:'s| are you| do you do| goes it)\b",
    r"^\bwhat'?s up\b",
    r"^\bgood\s+(?:morning|afternoon|evening|night)\b",
    r"^\bthanks?\b",
    r"^\bthank you\b",
    r"^\bye(?:ah|s|p)?\b",
    r"^\bok(?:ay)?\b",
    r"^\bsure\b",
    r"^\bnice\b",
    r"^\bcool\b",
    r"^\bwho are you\b",
    r"^\bwhat are you\b",
    r"^\bwhat can you do\b",
    r"^\bhelp\b",
    r"^\bbye\b",
    r"^\bgoodbye\b",
    r"^\bsee you\b",
    r"^\bhow (?:was|is|are) your day\b",
    r"^\bwhat (?:time|date|day) is it\b",
    r"^\btell me a joke\b",
    r"^\bhow old are you\b",
    r"^\bwhat('?s| is) your name\b",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _CONV_PATTERNS]


def is_conversational(text: str) -> bool:
    """Return True if *text* is chitchat / conversational rather than a task."""
    t = text.strip()
    if not t:
        return False
    # Very short inputs are likely conversational
    if len(t) <= 3:
        return True
    for pat in _COMPILED:
        if pat.search(t):
            return True
    return False
