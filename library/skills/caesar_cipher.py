"""Library pack: Caesar shift cipher (encode and decode)."""
from skills.registry import register


def _shift(s, k):
    out = []
    for ch in s:
        if ch.isalpha():
            base = ord("A") if ch.isupper() else ord("a")
            out.append(chr((ord(ch) - base + k) % 26 + base))
        else:
            out.append(ch)
    return "".join(out)


@register("caesar_cipher", [
    r"^(?:caesar|shift)\s+(?P<k>\d{1,2})\s*[:\-]?\s*(?P<text>.+)$",
    r"^decode\s+(?:caesar\s+)?shift\s+(?P<k>\d{1,2})\s*[:\-]?\s*(?P<text>.+)$",
], "Caesar cipher: 'caesar 5 hello'")
def skill_caesar(text, match):
    g = match.groupdict()
    k = int(g["k"]) % 26
    body = g["text"].strip()
    if text.lower().startswith("decode"):
        k = -k
    return _shift(body, k)
