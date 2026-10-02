"""Screen context skill — instant answers from the RAM-cached frame.

Unlike screen_ocr (fresh grab every time), this uses the background
capture loop's freshest frame, so it is effectively instant and never
hits the disk.
"""
from skills.registry import register


@register("screen_context", [
    r"^(?:what(?:'s|\s+is)\s+on\s+(?:my\s+|the\s+)?screen|"
    r"describe\s+(?:my\s+|the\s+)?screen|screen\s+context)[\?\.\!]?$",
    r"^(?:read|explain|fix)\s+(?:me\s+)?(?:this|the)\s+"
    r"(?:error|bug|exception|issue|message)[\?\.\!]?$",
], "Answer from what's currently on screen (RAM-cached frame)")
def skill_screen_context(text, match):
    try:
        from ai import screen_context
        q = None
        low = text.lower()
        if "error" in low or "bug" in low or "exception" in low or "explain" in low:
            q = ("Extract the error/exception text visible on this screen "
                 "verbatim, then briefly state its likely cause. Preserve "
                 "file names and line numbers.")
        r = screen_context.ask(q)
        if r.startswith("[error]"):
            return r
        return f"On your screen:\n{r[:900]}"
    except Exception as exc:
        return f"Screen context failed: {str(exc)[:100]}"


@register("screen_loop_control", [
    r"^(?:screen|capture)\s+loop\s+(on|off|status)[\?\.\!]?$",
], "Toggle / status of the background screen-context loop")
def skill_screen_loop(text, match):
    from ai import screen_context
    try:
        action = (match.group(1) or "").lower()
    except Exception:
        action = "status"
    if action == "on":
        return "Screen loop on." if screen_context.start() else "Could not start."
    if action == "off":
        screen_context.stop()
        return "Screen loop off."
    s = screen_context.status()
    return (f"Screen loop: {'running' if s['running'] else 'stopped'} · "
            f"{'enabled' if s['enabled'] else 'disabled'} · "
            f"last frame {s['age']}s ago ({s['size'] or 'n/a'}, RAM-only, "
            f"{s['captures']} captures).")
