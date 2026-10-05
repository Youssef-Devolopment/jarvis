"""Self-cleaning skill: report temp waste, remove it on confirm."""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

TIDY_PATTERNS = [
    r"^(?:tidy(?:\s+up)?|clean\s+(?:up\s+)?(?:the\s+)?temp(?:orary)?(?:\s+files)?|clear\s+temp(?:orary)?(?:\s+files)?)[\?\.\!]?$",
]


def _report(dry: bool) -> str:
    from system import tidy
    r = tidy.clean(dry_run=dry)
    if r["stale_files"] == 0:
        return "Temp is already clean — nothing older than 7 days."
    if dry:
        return (f"Temp holds {r['stale_files']} files "
                f"({r['stale_mb']} MB) older than 7 days. "
                f"Say 'tidy confirm' and I'll remove them.")
    tail = (f" ({r['skipped_errors']} in-use files skipped)."
            if r["skipped_errors"] else ".")
    if r.get("voice_pruned"):
        tail = tail.rstrip(".") + f", voice cache trimmed ({r['voice_pruned']} files)."
    return (f"Removed {r['removed']} temp files, "
            f"reclaimed {r['reclaimed_mb']} MB" + tail)


@register("tidy", TIDY_PATTERNS, "Report or remove old temp files")
def skill_tidy(text, m):
    try:
        return _report(dry=True)
    except Exception as exc:
        log.warning("tidy scan failed: %s", exc)
        return "Could not scan temp right now."


@register("tidy_confirm", [
    r"^(?:tidy\s+confirm|confirm\s+tidy)[\?\.\!]?$",
], "Remove old temp files (after tidy report)")
def skill_tidy_confirm(text, m):
    try:
        return _report(dry=False)
    except Exception as exc:
        log.warning("tidy clean failed: %s", exc)
        return "Could not clean temp right now."
