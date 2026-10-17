"""Color Converter module — hex, RGB and HSL math (no regex needed)."""
from skills.registry import register

_HEX_DIGITS = set("0123456789abcdefABCDEF")
_HINT = ("Tell me a hex color like #ff8800 and ask for rgb or hsl — "
         "try \"what color is #ff8800 in rgb\".")


def _rgb(hexstr):
    """'#f80' / '#ff8800' (with or without #) -> (r, g, b) or None."""
    h = hexstr.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) != 6 or not all(ch in _HEX_DIGITS for ch in h):
        return None
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(r, g, b):
    return "#{:02x}{:02x}{:02x}".format(r, g, b)


def _hsl(r, g, b):
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    light = (mx + mn) / 2.0
    if mx == mn:                       # grey
        return 0.0, 0.0, light
    d = mx - mn
    sat = d / (2.0 - mx - mn) if light > 0.5 else d / (mx + mn)
    if mx == rf:
        hue = ((gf - bf) / d + (6.0 if gf < bf else 0.0)) / 6.0
    elif mx == gf:
        hue = ((bf - rf) / d + 2.0) / 6.0
    else:
        hue = ((rf - gf) / d + 4.0) / 6.0
    return hue * 360.0, sat, light


def _answer(hexstr, target):
    rgb = _rgb(hexstr)
    if rgb is None:
        return None
    r, g, b = rgb
    if target == "hsl":
        h, s, light = _hsl(r, g, b)
        return (f"{_hex(r, g, b)} is hsl({h:.0f}, {s * 100:.0f}%, "
                f"{light * 100:.0f}%).")
    if target in ("rgb", "rgba"):
        return f"{_hex(r, g, b)} is rgb({r}, {g}, {b})."
    return None


@register("color_convert", [
    r"convert\s+(?:color\s+)?#([0-9a-fA-F]{3,8})\s+(?:to|into)\s+"
    r"(rgb|rgba|hsl)",
    r"what\s+color\s+is\s+#?([0-9a-fA-F]{3,8})\s+in\s+(rgb|rgba|hsl)",
], "Convert hex colors to RGB or HSL")
def skill_color_convert(text, match):
    reply = _answer("#" + match.group(1), match.group(2))
    return reply or _HINT
