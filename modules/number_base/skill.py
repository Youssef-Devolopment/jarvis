"""Number Base module — decimal, binary, octal and hex conversions."""
from skills.registry import register

_BASES = {"binary": 2, "bin": 2, "octal": 8, "oct": 8,
          "decimal": 10, "dec": 10, "hex": 16, "hexadecimal": 16}
_PREFIX = {2: "0b", 8: "0o", 16: "0x"}
_HINT = ("I convert between decimal, binary, octal and hex — try "
         "\"convert 255 to binary\" or \"what is 0xff in decimal\".")


def _parse(token):
    """'255' / '0xff' / '0b11' / '-12' -> int, or None."""
    t = token.strip().lower()
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    try:
        value = int(t, 0) if t[:2] in ("0x", "0b", "0o") else int(t, 10)
    except ValueError:
        return None
    return -value if neg else value


def _render(value, base):
    sign = "-" if value < 0 else ""
    body = format(abs(value), "b" if base == 2 else
                  "o" if base == 8 else
                  "x" if base == 16 else "d")
    return sign + (_PREFIX.get(base, "") + body if base != 10 else body)


@register("number_base", [
    r"convert\s+(-?\d+|0[xXbBoO][0-9a-fA-F]+)\s+to\s+"
    r"(binary|bin|octal|oct|hex|hexadecimal)",
    r"what\s+is\s+(-?\d+|0[xXbBoO][0-9a-fA-F]+)\s+in\s+"
    r"(binary|bin|octal|oct|hex|hexadecimal|decimal|dec)",
], "Convert numbers between decimal, binary, octal and hex")
def skill_number_base(text, match):
    value = _parse(match.group(1))
    if value is None:
        return _HINT
    base = _BASES[match.group(2)]
    return f"{match.group(1)} is {_render(value, base)}."
