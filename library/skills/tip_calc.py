"""Library pack: tip calculator (default 15%)."""
import math
from skills.registry import register


@register("tip_calc", [
    r"^tip\s+(?:on|for)\s+[$]?(?P<bill>\d+(?:\.\d+)?)(?:\s+at\s+(?P<pct>\d+(?:\.\d+)?)\s*%)?$",
    r"^(?P<pct>\d+(?:\.\d+)?)\s*%\s*tip\s+(?:on|for)\s+[$]?(?P<bill>\d+(?:\.\d+)?)$",
    r"^(?:what(?:'s| is)\s+(?:the\s+)?tip\s+on\s+[$]?(?P<bill2>\d+(?:\.\d+)?))$",
], "Tip: 'tip on 50 at 18%'")
def skill_tip(text, match):
    g = match.groupdict()
    bill = float(g.get("bill") or g.get("bill2"))
    pct = float(g["pct"]) if g.get("pct") else 15.0
    tip = math.floor(bill * pct / 100.0 * 100 + 0.5) / 100
    total = math.floor((bill + tip) * 100 + 0.5) / 100
    return f"Tip {pct:g}% on {bill:g} is {tip:g} — total {total:g}."
