"""Library pack: count words, characters and sentences in text."""
from skills.registry import register


@register("word_counter", [
    r"^count words (?:in|of)\s+(?P<text>.+)$",
    r"^how many words (?:are (?:there )?in|in)\s+(?P<text>.+)$",
    r"^word count\s*[:\-]?\s*(?P<text>.+)$",
], "Count words, characters and sentences in any text")
def skill_word_counter(text, match):
    body = match.group("text").strip()
    words = [w for w in body.split() if w]
    sentences = len([s for s in body.split(".") if s.strip()])
    chars = len(body)
    no_space = len(body.replace(" ", ""))
    return (f"{len(words)} words, {chars} characters "
            f"({no_space} without spaces), {sentences} sentences.")
