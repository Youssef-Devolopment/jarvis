import datetime as dt
from skills.registry import register


@register("time", [
    r"\bwhat(?:'s| is)?\s+the\s+time\b",
    r"\bwhat\s+time\s+is\s+it\b",
    r"\bcurrent\s+time\b",
    r"\btell\s+me\s+the\s+time\b",
], "Current time")
def skill_time(text, match):
    n = dt.datetime.now()
    return f"It is {n:%H:%M} — {n:%I:%M %p}."


@register("date", [
    r"\bwhat(?:'s| is)?\s+(?:the\s+)?date\b",
    r"\bwhat\s+day\s+is\s+it\b",
    r"\btoday'?s\s+date\b",
], "Today's date")
def skill_date(text, match):
    n = dt.datetime.now()
    return f"Today is {n:%A, %d %B %Y}."
