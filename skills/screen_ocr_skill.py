"""Screen OCR skill."""
from skills.registry import register

@register("screen_ocr", [
    r"^(?:read|grab|extract|copy)\s+(?:all\s+)?text\s+(?:from\s+(?:the\s+)?screen|on\s+screen)[\?\.\!]?$",
    r"^اقرأ\s+(?:النص|اللي)\s+(?:على|في)\s+(?:الشاشة)[\?\.\!]?$",
    r"^(?:ocr|ocr\s+screen)[\?\.\!]?$",
], "Extract text from screen")
def skill_screen_ocr(text, match):
    try:
        from ai import screen_text
        r = screen_text.extract_text()
        return r if r.startswith("[error]") else f"Text from screen:\n{r[:800]}"
    except Exception as exc:
        return f"OCR failed: {str(exc)[:100]}"
