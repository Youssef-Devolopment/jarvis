"""Close/kill a desktop application by name (graceful first)."""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

# tab/window belong to the browser/desktop hotkey skills (registered
# earlier, matched first) — the lookahead keeps this skill from ever
# hijacking them even if those handlers decline. Both "close tab"
# and "close the tab" shapes are excluded (regex backtracking would
# otherwise accept the latter as app="the tab").
CLOSE_PATTERNS = [
    r"^(?:close|kill)\s+(?:the\s+)?(?:app\s+)?"
    r"(?P<app>(?!tab\b|window\b|the\s+(?:tab\b|window\b)).+?)[\?\.\!]?$",
]


def _ask_close(display: str) -> bool:
    """Voice announcement + toast buttons. Standing yes in auto mode."""
    try:
        from system.app_learner import ask_user
        return bool(ask_user(display, verb="Close"))
    except Exception:
        return False


@register("close_app", CLOSE_PATTERNS, "Close a desktop application")
def skill_close(text, m):
    app = (m.group("app") or "").strip()
    if not app:
        return None
    try:
        from system import app_close
        res = app_close.close_by_name(app, ask_fn=_ask_close)
        return res.get("output")
    except Exception as exc:
        log.warning("close skill failed: %s", exc)
        return f"Could not close '{app}'."
