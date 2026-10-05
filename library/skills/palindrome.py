"""Library pack: palindrome check."""
import re
from skills.registry import register


@register("palindrome", [
    r"^(?:is\s+)?(?P<text>.+?)\s+a\s+palindrome[\?\.\!]?$",
    r"^palindrome\s+check\s*[:\-]?\s*(?P<text>.+)$",
], "Is it a palindrome? 'is racecar a palindrome'")
def skill_palindrome(text, match):
    body = match.group("text").strip()
    cleaned = re.sub(r"[^a-z0-9]", "", body.lower())
    if not cleaned:
        return None
    yes = cleaned == cleaned[::-1]
    if yes:
        return f"Yes — \"{body.strip()}\" is a palindrome."
    return f"No — \"{body.strip()}\" isn't a palindrome."
