"""Library pack: numbers <-> Roman numerals."""
from skills.registry import register

_VALS = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
         (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
         (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def _to_roman(n):
    out = []
    for v, sym in _VALS:
        while n >= v:
            out.append(sym)
            n -= v
    return "".join(out)


def _from_roman(s):
    s = s.upper()
    num, i = 0, 0
    while i < len(s):
        for v, sym in _VALS:
            if s.startswith(sym, i):
                num += v
                i += len(sym)
                break
        else:
            return None
    return num


@register("roman_numeral", [
    r"^roman numeral (?:for |of )?(?P<num>\d{1,4})$",
    r"^(?P<num>\d{1,4}) (?:in|to) roman numerals?$",
    r"^(?:what is |whats )?(?P<roman>[IVXLCDM]+) (?:in|as) (?:decimal|numbers?)$",
], "Roman numerals: 'roman numeral 1987'")
def skill_roman(text, match):
    g = match.groupdict()
    if g.get("num"):
        n = int(g["num"])
        if not 1 <= n <= 3999:
            return None
        return f"{n} is {_to_roman(n)}."
    val = _from_roman(g["roman"])
    if val is None or not 1 <= val <= 3999:
        return None
    return f"{g['roman'].upper()} is {val}."
