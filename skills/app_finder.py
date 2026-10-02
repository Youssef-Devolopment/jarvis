"""App finder — where is it installed, what apps do I have."""
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


@register("app_find", [
    r"^(?:where\s+is|find|locate)\s+(?P<app>.+?)\s+(?:installed|located)[\?\.\!]?$",
    r"^(?:list|show)\s+(?:my\s+|all\s+)?(?:installed\s+)?apps[\?\.\!]?$",
    r"^(?:what\s+)?apps\s+do\s+i\s+have[\?\.\!]?$",
], "Find apps and their exact paths")
def skill_app_find(text, match):
    try:
        from ai import app_index
        gd = match.groupdict()
        app = (gd.get("app") or "").strip()
        if app:
            hit = app_index.find(app)
            if hit:
                return (f"{hit['name']} is at {hit['path']} "
                        f"(from {hit['source']}).")
            return f"No app matching '{app}' in the index."
        apps = app_index.load_index()
        if not apps:
            return "No apps indexed."
        names = sorted({a["name"] for a in apps if a["name"]})[:15]
        return (f"{len(apps)} apps indexed, e.g.: "
                + ", ".join(names) + ".")
    except Exception as exc:
        return f"App index error: {str(exc)[:100]}"


@register("app_refresh", [
    r"^re(?:fresh|scan|build)(?:\s+the)?\s+app(?:s)?(?:\s+index)?[\?\.\!]?$",
], "Rescan installed apps")
def skill_app_refresh(text, match):
    try:
        from ai import app_index
        apps = app_index.refresh()
        return f"App index rebuilt: {len(apps)} apps."
    except Exception as exc:
        return f"Rescan failed: {str(exc)[:100]}"
