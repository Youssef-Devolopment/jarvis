"""Quick capture skill."""
from skills.registry import register

@register("quick_capture", [
    r"^(?:remind\s+me|فكرني|ذكرني)\s+.+",
    r"^(?:note|ملاحظة|احفظ\s+ملاحظة)\s*[:].+",
    r"^save\s+contact\s+.+",
    r"^احفظ\s+رقم\s+.+",
], "Quick capture — notes, todos, reminders, contacts")
def skill_quick_capture(text, match):
    try:
        from ai import quick_capture
        return quick_capture.execute(text).get("reply", "")
    except Exception as exc:
        return f"Capture failed: {str(exc)[:100]}"
