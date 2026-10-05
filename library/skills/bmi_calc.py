"""Library pack: BMI from weight (kg) and height (cm)."""
import math
from skills.registry import register


@register("bmi_calc", [
    r"^(?:calculate\s+|what(?:'s| is)\s+(?:my\s+)?)?bmi\s+(?:for\s+)?(?P<kg>\d+(?:\.\d+)?)\s*kg\s*(?:at\s*|,?\s*|x\s*)(?P<cm>\d+(?:\.\d+)?)\s*cm$",
    r"^bmi\s+(?P<kg>\d+(?:\.\d+)?)\s*/\s*(?P<cm>\d+(?:\.\d+)?)$",
], "BMI: 'bmi 70kg 175cm'")
def skill_bmi(text, match):
    kg = float(match.group("kg"))
    cm = float(match.group("cm"))
    if kg <= 0 or cm <= 0:
        return None
    m = cm / 100.0
    bmi = kg / (m * m)
    bmi = math.floor(bmi * 10 + 0.5) / 10
    if bmi < 18.5:
        band = "underweight"
    elif bmi < 25:
        band = "normal range"
    elif bmi < 30:
        band = "overweight"
    else:
        band = "obese"
    return f"BMI {bmi:g} — {band}."
