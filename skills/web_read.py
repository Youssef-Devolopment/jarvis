from logger import get_logger
from skills.registry import register

log = get_logger(__name__)


@register("web_read", [
    r"^(?:please\s+)?(?:read|summari[sz]e)\s+(?:me\s+)?(?:this|the)\s+(?:page|article|site)(?:\s+to\s+me)?[\?\.\!]?$",
    r"^what(?:'s| is)\s+on\s+(?:this|the)\s+(?:page|site)[\?\.\!]?$",
    r"^read\s+it\s+to\s+me[\?\.\!]?$",
], "Summarize current page")
def skill(text, match):
    from skills.browser_agent import get_agent
    from ai.client import get_client
    try:
        d = get_agent().get_text(max_chars=6000)
    except Exception as exc:
        return f"Could not read page: {exc}"
    t = (d.get("text") or "").strip()
    if not t:
        return "No readable text on the page."
    title = d.get("title") or "this page"
    try:
        c = get_client()
        resp = c._client.chat.completions.create(
            model=c.model,
            messages=[
                {"role": "system", "content": "Summarize in three short spoken-friendly sentences. No markdown."},
                {"role": "user", "content": f"Title: {title}\n\n{t}"},
            ],
            temperature=0.2, max_tokens=220)
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return f"Here is what the page says: {t[:400].rsplit(' ', 1)[0]}..."
