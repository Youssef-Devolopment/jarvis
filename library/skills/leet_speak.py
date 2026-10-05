"""Library pack: leetspeak translator."""
from skills.registry import register

_MAP = str.maketrans({
    "a": "4", "A": "4", "e": "3", "E": "3", "i": "1", "I": "1",
    "o": "0", "O": "0", "s": "5", "S": "5", "t": "7", "T": "7",
    "b": "8", "B": "8", "g": "9", "G": "9", "z": "2", "Z": "2",
})


@register("leet_speak", [
    r"^(?:in\s+)?(?:leet|l33t|leetspeak)\s*[:\-]?\s*(?P<text>.+)$",
    r"^(?:convert\s+(?:it\s+)?to\s+(?:leet|l33t))\s*[:\-]?\s*(?P<text>.+)$",
], "Leetspeak: 'leet hello'")
def skill_leet(text, match):
    body = match.group("text").strip()
    if not body:
        return None
    return body.translate(_MAP)
