"""Quick Capture — natural language to notes, todos, contacts, reminders."""

from __future__ import annotations
import re
from datetime import datetime, timedelta
from logger import get_logger

log = get_logger(__name__)


def _parse_when(text):
    now = datetime.now()
    low = text.lower()
    m = re.search(r"in\s+(\d+)\s*(minutes?|mins?|m|hours?|hrs?|h)", low)
    if m:
        n = int(m.group(1)); u = m.group(2)
        d = timedelta(hours=n) if u.startswith("h") else timedelta(minutes=n)
        return (now + d).isoformat(timespec="minutes")
    m = re.search(r"after\s+(\d+)\s*(minutes?|mins?|m|hours?|hrs?|h)", low)
    if m:
        n = int(m.group(1)); u = m.group(2)
        d = timedelta(hours=n) if u.startswith("h") else timedelta(minutes=n)
        return (now + d).isoformat(timespec="minutes")
    m = re.search(r"at\s+(\d{1,2})[:\.](\d{2})", low)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        t = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if t < now: t += timedelta(days=1)
        return t.isoformat(timespec="minutes")
    m = re.search(r"at\s+(\d{1,2})\s*(am|pm)", low)
    if m:
        hh = int(m.group(1)); ap = m.group(2)
        if ap == "pm" and hh < 12: hh += 12
        if ap == "am" and hh == 12: hh = 0
        t = now.replace(hour=hh, minute=0, second=0, microsecond=0)
        if t < now: t += timedelta(days=1)
        return t.isoformat(timespec="minutes")
    if "tomorrow" in low or "بكرة" in low:
        t = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return t.isoformat(timespec="minutes")
    if "tonight" in low or "الليلة" in low:
        t = now.replace(hour=20, minute=0, second=0, microsecond=0)
        if t < now: t += timedelta(days=1)
        return t.isoformat(timespec="minutes")
    return None


def detect_intent(text):
    t = (text or "").strip()
    if not t: return {"intent": "unknown"}
    low = t.lower()

    m = re.search(r"(?:save|add)\s+(?:contact\s+)?(?:for\s+)?([A-Z][A-Za-z0-9\u0600-\u06FF]{1,30})"
                  r"(?:\s+(?:phone|number|رقم)\s*:?\s*(\+?\d[\d\s\-.()]{5,18}))?", t)
    if m and "contact" in low:
        return {"intent": "contact", "name": m.group(1), "phone": (m.group(2) or "").strip()}
    m = re.search(r"(?:احفظ|سجّل)\s+رقم\s+([^\s:]+)\s+(\+?\d[\d\s\-.()]{5,18})", t)
    if m:
        return {"intent": "contact", "name": m.group(1).strip(), "phone": m.group(2).strip()}

    for pat in [r"(?:remind\s+me|فكرني|ذكرني)\s+(.+)", r"(?:reminder|تذكير)\s*[:]\s*(.+)"]:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return {"intent": "reminder", "text": m.group(1).strip(), "due": _parse_when(t)}

    for pat in [r"^(?:add\s+to\s+(?:my\s+)?todo|todo|task)\s*[:]?\s*(.+)",
                r"^(?:ضيف|أضف)\s+(?:في\s+)?(?:الـ)?tasks?\s*[:]?\s*(.+)"]:
        m = re.search(pat, t, re.IGNORECASE)
        if m: return {"intent": "todo", "text": m.group(1).strip()}

    for pat in [r"^(?:note|ملاحظة|احفظ\s+ملاحظة|احفظ)\s*[:]?\s*(.+)"]:
        m = re.search(pat, t, re.IGNORECASE)
        if m: return {"intent": "note", "text": m.group(1).strip()}

    return {"intent": "unknown"}


def execute(text):
    intent = detect_intent(text)
    k = intent.get("intent")
    if k == "contact":
        try:
            from memory import save_contact
            cid = save_contact(intent.get("name", ""), phone=intent.get("phone", ""))
            return {"ok": bool(cid), "reply": f"Saved contact: {intent['name']}"} if cid else {"ok": False, "reply": "Could not save contact."}
        except Exception as exc:
            return {"ok": False, "reply": f"Contact error: {exc}"}
    if k == "reminder":
        due = intent.get("due")
        if not due:
            return {"ok": False, "reply": "I need a time. Try 'in 10 minutes' or 'at 3pm'."}
        try:
            from memory import save_reminder
            rid = save_reminder(intent.get("text", ""), due)
            return {"ok": bool(rid), "reply": f"Reminder at {due[11:16]}: {intent['text'][:60]}"}
        except Exception as exc:
            return {"ok": False, "reply": f"Reminder error: {exc}"}
    if k == "todo":
        try:
            from skills.registry import dispatch
            r = dispatch(f"add to my todo {intent['text']}")
            return {"ok": True, "reply": r or "Todo added."}
        except Exception as exc:
            return {"ok": False, "reply": f"Todo error: {exc}"}
    if k == "note":
        try:
            from memory import remember
            remember(intent.get("text", ""), category="note", source="quick_capture")
            return {"ok": True, "reply": f"Noted: {intent['text'][:80]}"}
        except Exception as exc:
            return {"ok": False, "reply": f"Note error: {exc}"}
    return {"ok": False, "reply": "Could not understand what to save."}
