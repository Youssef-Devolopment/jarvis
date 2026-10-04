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


def _auto_ask(display: str) -> bool:
    """Standing yes when auto mode is on, otherwise voice+toast."""
    try:
        from system.app_learner import auto_mode
        if auto_mode():
            return True
    except Exception:
        pass
    return _ask(display)


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
        elif _auto_ask(r.get("display") or app):
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
    # Fallback: exact path from the auto-discovered app index
    # (taskbar, running apps, desktop shortcuts the resolver misses).
    try:
        from ai import app_index
        hit = app_index.find(app)
        if hit and hit.get("path"):
            target = hit["path"]
            if L.is_instant(target):
                out = L.launch_target(target)
            elif _auto_ask(hit.get("name") or app):
                out = L.launch_target(target)
            else:
                return "OK, not opening it."
            try:
                from memory import context as ctx
                ctx.log_event("app", f"launched {app} via index")
            except Exception:
                pass
            return out
    except Exception:
        pass
    # Fallback: autonomous app learner — deep-scans Program Files,
    # LocalAppData, Start Menu and %PATH%; on a hit it launches the
    # app AND writes a permanent skill for it.
    try:
        from system import app_learner
        res = app_learner.learn_and_launch(app, ask_fn=_auto_ask)
        if res:
            if res.get("declined"):
                return "OK, not opening it."
            out = res.get("output") or f"Opened {app}."
            if res.get("staged"):
                out += (f"  [learned: '{res['name']}' — skill drafted, "
                        f"awaiting approval]")
            elif res.get("created"):
                out += f"  [learned: '{res['name']}' is now a skill]"
            return out
    except Exception as exc:
        log.warning("app learner fallback failed: %s", exc)
    return f"Could not find an app called '{app}'."
