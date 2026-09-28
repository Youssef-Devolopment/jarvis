"""Decide which escalation level a query needs."""

from __future__ import annotations
import re
from moods.levels import Level
from logger import get_logger

log = get_logger(__name__)

# Words that immediately trigger Council+
COUNCIL_TRIGGERS = [
    r"\b(?:compare|contrast)\b",
    r"\b(?:vs|versus)\b",
    r"\bwhich\s+(?:is|one)\s+(?:better|best)\b",
    r"\b(?:should\s+i|would\s+you)\s+(?:choose|pick|buy|get)\b",
    r"\b(?:recommend|advise|suggest)\b",
    r"\b(?:best|worst)\s+\w+\s+for\b",
    r"\b(?:pros|cons|advantages|disadvantages)\b",
    r"\b(?:trade.?offs?)\b",
]

MAX_TRIGGERS = [
    r"\bstrateg(?:y|ic)\b",
    r"\b(?:architecture|design)\b.*\b(?:system|software)\b",
    r"\b(?:long.?term|longterm)\b",
    r"\b(?:business|investment)\s+decision\b",
    r"\b(?:multi.?step)\b",
    r"\b(?:philosophical|existential)\b",
]

DEEP_TRIGGERS = [
    r"\b(?:explain|analyze|analyz|investigate)\b",
    r"\b(?:why|how)\s+does\b",
    r"\b(?:step.by.step)\b",
    r"\b(?:reason|reasoning)\b",
    r"\b(?:calculate|compute|derive|prove)\b",
    r"\b(?:debug|diagnose)\b",
]

SIMPLE_TRIGGERS = [
    r"^\s*(?:hi|hello|hey|thanks|thank you)\b",
    r"\b(?:what time|what day|what'?s the date)\b",
    r"\b(?:weather|temperature)\b",
    r"\b(?:convert|calculation)\b",
    r"^\s*[\d\s\+\-\*/\(\)]+\s*$",
]

_COUNCIL = [re.compile(p, re.IGNORECASE) for p in COUNCIL_TRIGGERS]
_MAX = [re.compile(p, re.IGNORECASE) for p in MAX_TRIGGERS]
_DEEP = [re.compile(p, re.IGNORECASE) for p in DEEP_TRIGGERS]
_SIMPLE = [re.compile(p, re.IGNORECASE) for p in SIMPLE_TRIGGERS]


def classify(text: str, prev_failed_level: Level = None) -> Level:
    """Return the level needed for this query."""
    if not text:
        return Level.QUICK

    t = text.strip()
    low = t.lower()

    # Simple check first
    for pat in _SIMPLE:
        if pat.search(t):
            return Level.QUICK

    # Escalation from previous failed attempt
    if prev_failed_level is not None:
        return Level(min(int(prev_failed_level) + 1, int(Level.COUNCIL_XTREME)))

    # Council+ / Max triggers
    if any(p.search(t) for p in _MAX):
        return Level.COUNCIL_PLUS
    if any(p.search(t) for p in _COUNCIL):
        return Level.COUNCIL

    # Length signal
    word_count = len(t.split())
    if word_count > 200:
        return Level.COUNCIL
    if word_count > 80:
        return Level.DEEP

    # Deep triggers
    if any(p.search(t) for p in _DEEP):
        return Level.DEEP

    # Question marks
    if t.count("?") >= 3:
        return Level.DEEP

    return Level.STANDARD


def council_models_for_level(level: Level) -> tuple:
    from moods.levels import LEVEL_SPECS
    return LEVEL_SPECS[level].models


def needs_user_confirmation(level: Level) -> bool:
    """Levels 7+ should ask before running (expensive)."""
    return int(level) >= int(Level.COUNCIL_MAX)
