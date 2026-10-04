"""One-click local backup: memory DB + .env zipped, last 5 kept."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_BACKUP_DIR = _ROOT / "logs" / "backups"
_KEEP = 5


def create_backup(root: Path | None = None,
                  backup_dir: Path | None = None,
                  keep: int = _KEEP) -> dict:
    """Zip memory DB + .env. Never raises for expected cases."""
    root = Path(root) if root else _ROOT
    dest = Path(backup_dir) if backup_dir else _BACKUP_DIR
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return {"ok": False, "error": f"backup dir failed: {exc}"[:120]}
    import zipfile
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    fp = dest / f"jarvis-backup-{ts}.zip"
    files, total = [], 0
    for rel in ("memory/jarvis_memory.db", ".env"):
        src = root / rel
        try:
            if src.is_file():
                files.append(rel)
                total += src.stat().st_size
        except Exception:
            continue
    if not files:
        return {"ok": False, "error": "nothing to back up"}
    try:
        with zipfile.ZipFile(fp, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in files:
                z.write(root / rel, rel)
    except Exception as exc:
        return {"ok": False, "error": f"zip failed: {exc}"[:120]}
    try:
        olds = sorted(dest.glob("jarvis-backup-*.zip"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in olds[keep:]:
            try:
                stale.unlink()
            except Exception:
                continue
    except Exception:
        pass
    log.info("Backup written: %s (%d files)", fp.name, len(files))
    return {"ok": True, "path": str(fp), "files": files,
            "kb": round(total / 1024, 1)}


def list_backups(backup_dir: Path | None = None) -> list[dict]:
    dest = Path(backup_dir) if backup_dir else _BACKUP_DIR
    try:
        return [{"file": p.name,
                 "kb": round(p.stat().st_size / 1024, 1)}
                for p in sorted(dest.glob("jarvis-backup-*.zip"),
                                key=lambda p: p.stat().st_mtime,
                                reverse=True)]
    except Exception:
        return []
