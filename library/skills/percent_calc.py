"""Library pack: quick percentages."""
import math
from skills.registry import register


@register("percent_calc", [
    r"^(?P<p>\d+(?:\.\d+)?)\s*%\s*of\s+(?P<n>\d+(?:\.\d+)?)$",
    r"^(?:what(?:'s| is)\s+)?(?P<p>\d+(?:\.\d+)?)\s*percent of\s+(?P<n>\d+(?:\.\d+)?)$",
], "Percentages: '20% of 150'")
def skill_percent(text, match):
    p = float(match.group("p"))
    n = float(match.group("n"))
    out = p * n / 100.0
    out = math.floor(out * 100 + 0.5) / 100
    return f"{p}% of {n} is {out:g}."
