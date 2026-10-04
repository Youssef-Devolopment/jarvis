"""Dream Mode — nightly autonomous routine."""

from __future__ import annotations
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_DREAM_LOG = _ROOT / "logs" / "dream_mode.log"
_TRASH = _ROOT / "logs" / "dream_trash"
_REPORTS = _ROOT / "logs" / "dream_reports"

_TRASH.mkdir(parents=True, exist_ok=True)
_REPORTS.mkdir(parents=True, exist_ok=True)

# File categories by extension
CATEGORIES = {
    "images":   {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg"},
    "videos":   {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"},
    "audio":    {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"},
    "docs":     {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"},
    "sheets":   {".xls", ".xlsx", ".csv", ".ods"},
    "code":     {".py", ".js", ".ts", ".html", ".css", ".json", ".xml",
                 ".yaml", ".yml", ".cpp", ".c", ".java", ".go", ".rs"},
    "archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"},
    "installers": {".exe", ".msi", ".dmg", ".deb", ".rpm"},
}

# Age threshold — only organize files older than this
MIN_AGE_DAYS = 1

# Folders safe to organize
SAFE_FOLDERS = [
    Path.home() / "Desktop",
    Path.home() / "Downloads",
    Path.home() / "Documents",
]


def _audit(action: str, detail: str):
    try:
        with _DREAM_LOG.open("a", encoding="utf-8") as f:
            ts = datetime.now().isoformat(timespec="seconds")
            f.write(f"[{ts}] {action:12} {detail}\n")
    except Exception:
        pass


def _category_for(path: Path) -> str:
    ext = path.suffix.lower()
    for cat, exts in CATEGORIES.items():
        if ext in exts:
            return cat
    return "misc"


def _is_user_active() -> bool:
    """Check if user has been active recently."""
    # Simple heuristic: if any file in Desktop modified in last 5 min
    try:
        cutoff = time.time() - 300
        for folder in SAFE_FOLDERS:
            if not folder.exists():
                continue
            try:
                for p in folder.iterdir():
                    if p.is_file() and p.stat().st_mtime > cutoff:
                        return True
            except Exception:
                continue
        return False
    except Exception:
        return False


def _move_safe(src: Path, dst: Path) -> bool:
    """Move a file safely. Returns True on success."""
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        # If target exists, add timestamp
        if dst.exists():
            ts = int(time.time())
            dst = dst.with_name(f"{dst.stem}_{ts}{dst.suffix}")
        shutil.move(str(src), str(dst))
        _audit("MOVE", f"{src} -> {dst}")
        return True
    except Exception as exc:
        _audit("ERROR", f"{src}: {exc}")
        return False


def organize_folder(folder: Path, dry_run: bool = False) -> dict:
    """Sort files in a folder by category."""
    if not folder.exists() or not folder.is_dir():
        return {"folder": str(folder), "moved": 0, "skipped": 0, "errors": 0}

    moved = 0
    skipped = 0
    errors = 0
    cutoff = time.time() - (MIN_AGE_DAYS * 86400)
    organized_root = folder / "_organized"

    try:
        items = list(folder.iterdir())
    except Exception:
        return {"folder": str(folder), "moved": 0, "skipped": 0, "errors": 0}

    for item in items:
        if not item.is_file():
            continue
        if item.name.startswith("."):
            skipped += 1
            continue
        try:
            st = item.stat()
            if st.st_mtime > cutoff:
                skipped += 1
                continue
        except Exception:
            skipped += 1
            continue

        cat = _category_for(item)
        target = organized_root / cat / item.name

        if dry_run:
            _audit("DRYRUN", f"{item} -> {target}")
            moved += 1
            continue

        if _move_safe(item, target):
            moved += 1
        else:
            errors += 1

    return {
        "folder": str(folder),
        "moved": moved,
        "skipped": skipped,
        "errors": errors,
    }


def backup_memory() -> dict:
    """Backup memory DB and preferences."""
    try:
        mem = _ROOT / "memory" / "jarvis_memory.db"
        if not mem.exists():
            return {"ok": False, "reason": "no memory db"}

        backups_dir = _ROOT / "logs" / "memory_backups"
        backups_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = backups_dir / f"jarvis_memory_{ts}.db"

        shutil.copy2(mem, dest)
        _audit("BACKUP", str(dest))

        # Keep only last 7 backups
        backups = sorted(backups_dir.glob("jarvis_memory_*.db"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for old in backups[7:]:
            try:
                old.unlink()
            except Exception:
                pass

        return {"ok": True, "file": str(dest),
                "size_kb": round(dest.stat().st_size / 1024, 1)}
    except Exception as exc:
        log.exception("Backup failed: %s", exc)
        return {"ok": False, "reason": str(exc)[:100]}


def summarize_day() -> str:
    """Summarize what happened today from context log."""
    try:
        from memory import context
        events = context.recent_events(minutes=24 * 60, limit=200)
        if not events:
            return "No recorded activity today."

        # Group by kind
        by_kind = {}
        for e in events:
            k = e.get("kind", "other")
            by_kind[k] = by_kind.get(k, 0) + 1

        # Get apps used
        apps = [e["detail"].replace("launched ", "").replace("focused ", "")
                for e in events if e.get("kind") == "app"]
        unique_apps = list(set(apps))[:5]

        # Ask LLM for a friendly summary
        summary_input = (
            f"Today's activity summary:\n"
            f"- Total actions: {len(events)}\n"
            f"- By type: {by_kind}\n"
            f"- Apps used: {unique_apps}\n"
            f"- Time range: {events[-1]['timestamp'][11:16]} to "
            f"{events[0]['timestamp'][11:16]}\n"
        )
        try:
            from ai.client import get_client
            c = get_client()
            model = getattr(c, "model", None) or c.default_model
            r = c._client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system",
                     "content": "Summarize the user's day in 2 sentences. "
                                "Be conversational, no markdown."},
                    {"role": "user", "content": summary_input},
                ],
                max_tokens=120,
                temperature=0.3,
            )
            return (r.choices[0].message.content or "").strip()
        except Exception:
            return (f"You did {len(events)} actions today, "
                    f"mostly in {', '.join(unique_apps[:3])}.")
    except Exception as exc:
        log.exception("Summarize failed: %s", exc)
        return "Could not summarize day."


def run_dream(dry_run: bool = False) -> dict:
    """Full dream mode run."""
    log.info("Dream Mode starting (dry_run=%s)", dry_run)
    _audit("START", f"dry_run={dry_run}")
    t0 = time.time()

    report = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "dry_run": dry_run,
    }

    # 1. Check if user is active
    if _is_user_active() and not dry_run:
        _audit("SKIP", "user is active")
        return {"ok": False, "reason": "user active"}

    # 2. Organize folders
    folders_report = []
    try:
        from memory import get_pref
        do_desktop = get_pref("dream_organize_desktop", True)
        do_downloads = get_pref("dream_organize_downloads", True)
    except Exception:
        do_desktop = do_downloads = True

    if do_desktop:
        r = organize_folder(Path.home() / "Desktop", dry_run)
        folders_report.append(r)
    if do_downloads:
        r = organize_folder(Path.home() / "Downloads", dry_run)
        folders_report.append(r)

    report["folders"] = folders_report

    # 2.5 Tidy temp files (self-cleaning while the user is away)
    if not dry_run:
        try:
            from memory import get_pref
            if get_pref("dream_tidy_temp", True):
                from system import tidy as _tidy
                t = _tidy.clean(dry_run=False)
                t.update(_tidy.prune_dream_reports())
                report["tidy"] = t
                _audit("TIDY", f"removed={t['removed']} "
                               f"reclaimed={t['reclaimed_mb']}MB")
        except Exception as exc:
            log.warning("Dream tidy failed: %s", exc)

    # 3. Backup memory
    if not dry_run:
        try:
            from memory import get_pref
            if get_pref("dream_backup_memory", True):
                report["backup"] = backup_memory()
        except Exception:
            pass

    # 4. Summarize day
    if not dry_run:
        try:
            from memory import get_pref
            if get_pref("dream_summarize_day", True):
                report["day_summary"] = summarize_day()
        except Exception:
            pass

    # 5. Save report
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = _REPORTS / f"dream_{ts}.json"
        import json
        report_file.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8")
        report["report_file"] = str(report_file)
    except Exception as exc:
        log.warning("Could not save report: %s", exc)

    elapsed = round(time.time() - t0, 2)
    report["elapsed"] = elapsed
    report["ok"] = True

    total_moved = sum(f.get("moved", 0) for f in folders_report)
    _audit("DONE", f"moved={total_moved} elapsed={elapsed}s")

    log.info("Dream Mode done in %.1fs, moved %d files",
             elapsed, total_moved)
    return report


def get_last_report() -> dict:
    """Read the most recent dream report."""
    try:
        reports = sorted(_REPORTS.glob("dream_*.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            return {}
        import json
        return json.loads(reports[0].read_text(encoding="utf-8"))
    except Exception:
        return {}
