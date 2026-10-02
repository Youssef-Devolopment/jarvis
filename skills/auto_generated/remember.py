from skills.registry import register

@register("remember", [
    r"(?i)^\s*(?:please\s+)?rem(?:ember|ind me)(?:\s+that)?\s*[:,]?\s*(?P<fact>.+?)\s*$",
    r"(?i)^\s*(?:please\s+)?(?:make a note|note|keep in mind)(?:\s+that)?\s*[:,]?\s*(?P<fact>.+?)\s*$",
    r"(?i)^\s*(?:don'?t forget|never forget)\s*[:,]?\s*(?P<fact>.+?)\s*$",
], "Remembers a fact the user asks to store")
def remember(text, match):
    fact = (match.group("fact") or "").strip(" .,!?:;-")
    if not fact:
        return None
    if len(fact) > 200:
        fact = fact[:200].rstrip() + "..."
    return "Got it, I'll remember that {}.".format(fact)