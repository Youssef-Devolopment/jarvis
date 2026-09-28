"""Launch ANY desktop application (universal resolver)."""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_SITE_HINTS = (".com", ".org", ".net", ".io", "http", "www", "site",
               "website")


def _ask(display: str) -> bool:
    """Voice announcement + toast buttons. Default NO."""
    try:
        from voice import speak_async
        speak_async(f"Open {display}? Say yes, or press Approve.")
    except Exception:
        pass
    try:
        from system.notify import confirm
        return bool(confirm(f"Open {display}?", timeout=60))
    except Exception:
        return False


@register("launch_app", [
    r"^(?:open|launch|start|run)\s+(?:the\s+)?(?:app\s+)?(?P<app>.+?)[\?\.\!]?$",
], "Launch a desktop application")
def skill_launch(text, m):
    from system import launch as L
    app = (m.group("app") or "").strip()
    if not app:
        return None
    if any(x in app.lower() for x in _SITE_HINTS):
        return None  # websites belong to web_open
    if "://" in app or app.lower().split(":", 1)[0] in (
            "http", "https", "file", "javascript", "data", "ftp"):
        return None  # any url-like input belongs to web_open
    r = L.resolve_app(app)
    if r["status"] == "found":
        target = r["target"]
        if L.is_instant(target):
            out = L.launch_target(target)
        elif _ask(r.get("display") or app):
            out = L.launch_target(target)
        else:
            return "OK, not opening it."
        try:
            from memory import context as ctx
            ctx.log_event("app", f"launched {app}")
        except Exception:
            pass
        try:
            from skills.code_mode import _audit
            _audit("launch", target, True, app)
        except Exception:
            pass
        return out
    if r["status"] == "candidates":
        return ("Did you mean: "
                + ", ".join(r["candidates"]) + "?")
    return f"Could not find an app called '{app}'."
