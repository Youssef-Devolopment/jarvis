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


RESTORE_PATTERNS = [
    r"^(?:restore|recover)(?:\s+(?:my\s+)?(?:backup|memory|everything))?"
    r"(?:\s+backup)?[\?\.\!]?$",
    r"^(?:restore|recover)(?:\s+(?:my\s+)?backup)?\s+confirm[\?\.\!]?$",
]


@register("restore_backup", RESTORE_PATTERNS,
          "Restore memory and keys from a backup")
def skill_restore(text, m):
    import re
    low = (text or "").strip().lower()
    wants_confirm = bool(re.search(r"\bconfirm\b", low))
    try:
        from system import backup as _b
        res = _b.restore_backup(confirm=wants_confirm)
        if wants_confirm:
            if not res.get("ok"):
                return f"Restore failed: {res.get('error', 'unknown')}"
            return (f"Restored {', '.join(res['restored'])} from "
                    f"{res['file']}. Your previous state was saved to "
                    f"{res.get('safety_backup') or 'a fresh backup'}.")
        if not res.get("backups"):
            return "There are no backups to restore yet — say 'backup' first."
        newest = res.get("newest")
        n = len(res["backups"])
        return (f"I found {n} backup(s); newest is {newest}. "
                f"This replaces current memory and keys. "
                f"Say 'restore confirm' to apply the newest.")
    except Exception as exc:
        log.warning("restore skill failed: %s", exc)
        return "Restore failed before it started."
