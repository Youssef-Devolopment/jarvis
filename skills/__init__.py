from skills.base import Skill
from skills.registry import (all_skills, dispatch, get_skill, toggle_skill,
                             unregister)
from logger import get_logger

log = get_logger(__name__)

# Core skill modules, in dispatch-priority order. Each module registers
# itself on import. Loaded one-by-one so a single broken file can never
# take the whole package (and the server) down with it — the failure is
# logged and boot continues with the rest.
_CORE_SKILLS = [
    "web_search", "clock", "math_skill", "system", "system_control",
    "browser_keyboard", "desktop_keyboard", "desktop_mouse", "vision",
    "app_launcher", "app_closer", "weather", "wiki", "crypto",
    "translate", "routine_dictionary", "routine_fx", "routine_quotes",
    "routine_timers", "routine_notes", "routine_todo", "routine_convert",
    "routine_news", "dog_api", "whatsapp_web", "gmail_api",
    "vscode_open", "todoist_api", "mcp_manager", "clawbot_bridge",
    "openhands_bridge", "code_mode", "opencode_bridge",
    "interpreter_hand", "web_open", "web_read", "web_screenshot",
    "folder_sentinel", "win_target", "bridge_skill", "app_finder",
    "site_finder", "quick_capture_skill", "screen_ocr_skill",
    "screen_context_skill", "focus_lock_skill", "snippets_skill",
    "tidy_skill", "auto_generated",
]


def _load_modules(names):
    """Import skill modules by name. Returns (loaded, failed)."""
    import importlib
    loaded, failed = [], []
    for _mod in names:
        try:
            importlib.import_module(f"skills.{_mod}")
            loaded.append(_mod)
        except Exception as exc:
            failed.append(_mod)
            log.warning("skill module '%s' failed to load: %s",
                        _mod, str(exc)[:160])
    return loaded, failed


_load_modules(_CORE_SKILLS)
from plugins import load_plugins as _load_community_plugins  # noqa: F401

__all__ = ["Skill", "all_skills", "dispatch", "get_skill", "toggle_skill",
           "unregister"]
