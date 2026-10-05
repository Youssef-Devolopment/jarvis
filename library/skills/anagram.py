"""Library pack: anagram check."""
import re
from skills.registry import register


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


@register("anagram", [
    r"^are\s+(?P<a>.+?)\s+and\s+(?P<b>.+?)\s+anagrams?[\?\.\!]?$",
    r"^(?:is\s+)?(?P<a>.+?)\s+an\s+anagram\s+of\s+(?P<b>.+?)[\?\.\!]?$",
    r"^(?:check\s+(?:for\s+)?anagram\s*[:\-]?\s*)(?P<a>.+?)\s*[,/]\s*(?P<b>.+)$",
], "Anagrams: 'are silent and listen anagrams'")
def skill_anagram(text, match):
    g = match.groupdict()
    a, b = _norm(g["a"]), _norm(g["b"])
    if not a or not b:
        return None
    if sorted(a) == sorted(b):
        return f"Yes — \"{g['a'].strip()}\" and \"{g['b'].strip()}\" are anagrams."
    return f"No — \"{g['a'].strip()}\" and \"{g['b'].strip()}\" aren't anagrams."
