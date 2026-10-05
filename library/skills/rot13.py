"""Library pack: ROT13 encode/decode."""
from skills.registry import register


def _rot13(s):
    out = []
    for ch in s:
        o = ord(ch)
        if 65 <= o <= 90:
            out.append(chr((o - 65 + 13) % 26 + 65))
        elif 97 <= o <= 122:
            out.append(chr((o - 97 + 13) % 26 + 97))
        else:
            out.append(ch)
    return "".join(out)


@register("rot13", [
    r"^(?:rot13|rot-13)\s*[:\-]?\s*(?P<text>.+)$",
], "ROT13 cipher: 'rot13 hello'")
def skill_rot13(text, match):
    return _rot13(match.group("text").strip())
