"""Library pack: day of the week for a date."""
from datetime import date, timedelta
from skills.registry import register


def _parse(s):
    try:
        y, m, d = [int(x) for x in s.split("-")]
        return date(y, m, d)
    except Exception:
        return None


@register("weekday", [
    r"^what\s+(?:day|weekday)\s+(?:is|will\s+be|was)\s+(?P<date>\d{4}-\d{2}-\d{2})$",
    r"^(?:day of the week|weekday)\s*[:\-]?\s*(?P<date>\d{4}-\d{2}-\d{2})$",
    r"^what\s+day\s+(?:is|was)\s+(?P<when>today|tomorrow)$",
], "Weekday: 'what day is 2026-12-25'")
def skill_weekday(text, match):
    g = match.groupdict()
    if g.get("when"):
        target = date.today()
        if g["when"] == "tomorrow":
            target += timedelta(days=1)
    else:
        target = _parse(g["date"])
        if not target:
            return None
    return (f"{target.isoformat()} is a "
            f"{target.strftime('%A')} "
            f"({target.strftime('%B %d, %Y')}).")
