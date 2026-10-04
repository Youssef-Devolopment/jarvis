"""Back up memory + keys on demand."""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

BACKUP_PATTERNS = [
    r"^(?:back\s*up|backup)(?:\s+(?:my\s+)?(?:memory|everything|all|jarvis))?[\?\.\!]?$",
]


@register("backup_now", BACKUP_PATTERNS, "Back up memory and keys")
def skill_backup(text, m):
    try:
        from system import backup as _b
        res = _b.create_backup()
        if not res.get("ok"):
            return f"Backup failed: {res.get('error', 'unknown error')}"
        return (f"Backed up {len(res['files'])} files "
                f"({res['kb']} KB): {res['path']}")
    except Exception as exc:
        log.warning("backup skill failed: %s", exc)
        return "Backup failed before it started."
