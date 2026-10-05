"""Library pack: days until / since a date."""
from datetime import date
from skills.registry import register


def _parse(s):
    try:
        y, m, d = [int(x) for x in s.split("-")]
        return date(y, m, d)
    except Exception:
        return None


@register("date_diff", [
    r"^how many days (?:until|to)\s+(?P<date>\d{4}-\d{2}-\d{2})$",
    r"^days (?:until|to)\s+(?P<date>\d{4}-\d{2}-\d{2})$",
    r"^days since\s+(?P<date>\d{4}-\d{2}-\d{2})$",
], "Countdown: 'days until 2026-12-25'")
def skill_date_diff(text, match):
    target = _parse(match.group("date"))
    if not target:
        return None
    today = date.today()
    delta = (target - today).days
    if delta > 0:
        return f"{delta} days until {target.isoformat()}."
    if delta < 0:
        return f"{-delta} days since {target.isoformat()}."
    return f"That's today, {target.isoformat()}."
