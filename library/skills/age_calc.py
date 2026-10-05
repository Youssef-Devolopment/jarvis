"""Library pack: exact age from a birth date."""
from datetime import date
from skills.registry import register


@register("age_calc", [
    r"^(?:what(?:'s| is)\s+(?:the\s+)?age\s+(?:of\s+|for\s+)?)?(?:someone\s+born\s+|born\s+)(?P<date>\d{4}-\d{2}-\d{2})$",
    r"^age if born\s+(?P<date>\d{4}-\d{2}-\d{2})$",
    r"^how old (?:would|will) .{0,40} be (?:now|today|on \d{4}-\d{2}-\d{2})$",
], "Age: 'age if born 2000-05-14'")
def skill_age(text, match):
    g = match.groupdict()
    if not g.get("date"):
        return None
    try:
        y, m, d = [int(x) for x in g["date"].split("-")]
        born = date(y, m, d)
    except Exception:
        return None
    today = date.today()
    years = today.year - born.year
    if (today.month, today.day) < (born.month, born.day):
        years -= 1
    if years < 0:
        return "That date is in the future."
    days = (today - born).days
    return f"{years} years old ({days} days since {born.isoformat()})."
