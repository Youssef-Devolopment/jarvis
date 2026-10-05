"""Library pack: pretty-print messy JSON."""
import json
from skills.registry import register


@register("json_format", [
    r"^(?:format|pretty|prettify|beautify)\s+(?:the\s+)?json\s*[:\-]?\s*(?P<blob>.+)$",
    r"^json\s+format\s*[:\-]?\s*(?P<blob>.+)$",
], "Pretty-print JSON: 'format json {...}'")
def skill_json_format(text, match):
    blob = match.group("blob").strip()
    try:
        obj = json.loads(blob)
    except Exception:
        return None
    return json.dumps(obj, indent=2, ensure_ascii=False)
