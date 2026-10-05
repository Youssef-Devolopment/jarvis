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


# Members restore understands (relative to project root).
_RESTORABLE = ("memory/jarvis_memory.db", ".env")


def _close_db() -> None:
    """Drop the live SQLite handle so the file can be swapped."""
    try:
        from memory import store
        store.close_conn()
    except Exception:
        pass


def _put_back(src: Path, dest: Path) -> None:
    """Copy src over dest atomically (sidecar + rename). dest may be
    locked — raises to the caller, never half-writes."""
    side = dest.with_name(dest.name + ".restoring")
    try:
        import shutil
        shutil.copy2(src, side)
        import os
        os.replace(side, dest)
    finally:
        try:
            side.unlink(missing_ok=True)
        except Exception:
            pass


def restore_backup(filename: str | None = None, *, confirm: bool = False,
                   root: Path | None = None,
                   backup_dir: Path | None = None,
                   close_db=_close_db) -> dict:
    """Restore a backup zip over the project. Without confirm=True it
    only lists what would be restored (safe preview). A fresh safety
    backup of the CURRENT state is taken first; zip-slip is refused."""
    root = Path(root) if root else _ROOT
    dest = Path(backup_dir) if backup_dir else _BACKUP_DIR

    if not confirm:
        items = list_backups(dest)
        return {"ok": True, "needs_confirm": True,
                "newest": items[0]["file"] if items else None,
                "backups": items}

    name = (filename or "").strip()
    if not name:
        items = list_backups(dest)
        if not items:
            return {"ok": False, "error": "no backups found"}
        name = items[0]["file"]
    # Hard validation: plain filename inside the backup dir only.
    if (name != Path(name).name or "/" in name or "\\" in name
            or ".." in name or not name.startswith("jarvis-backup-")
            or not name.endswith(".zip")):
        return {"ok": False, "error": "invalid backup name"}
    fp = dest / name
    if not fp.is_file():
        return {"ok": False, "error": f"backup not found: {name}"}

    # 1) Extract with a zip-slip guard. This is deliberately done
    #    BEFORE the safety snapshot: backup names are minute-granular,
    #    so a same-minute snapshot would overwrite the very zip we are
    #    about to restore. Extracting first makes that harmless.
    import tempfile
    import zipfile
    tmp = Path(tempfile.mkdtemp(prefix="jarvis-restore-"))
    try:
        try:
            with zipfile.ZipFile(fp) as z:
                for zi in z.infolist():
                    n = zi.filename
                    if (n.startswith(("/", "\\")) or ":" in n
                            or ".." in Path(n).parts):
                        return {"ok": False, "error": "backup zip is unsafe"}
                z.extractall(tmp)
        except zipfile.BadZipFile:
            return {"ok": False, "error": "backup is not a valid zip"}

        # 2) Safety net: snapshot CURRENT state before touching anything.
        safety = create_backup(root=root, backup_dir=dest)
        safety_path = safety.get("path") if safety.get("ok") else None

        # 3) Swap in every member we understand.
        restored = []
        for rel in _RESTORABLE:
            src = tmp / rel
            if not src.is_file():
                continue
            target = root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            if rel.endswith(".db"):
                close_db()          # release the live handle first
                for side in (Path(str(target) + "-wal"),
                             Path(str(target) + "-shm")):
                    try:
                        side.unlink(missing_ok=True)
                    except Exception:
                        pass
            try:
                _put_back(src, target)
            except OSError as exc:
                return {"ok": False, "restored": restored,
                        "error": f"{rel} is locked: {exc}"[:150],
                        "safety_backup": safety_path}
            restored.append(rel)

        if not restored:
            return {"ok": False, "error": "backup contains no restorable files"}
        log.warning("Restored %s from %s (safety: %s)",
                    ", ".join(restored), name, safety_path or "none")
        return {"ok": True, "restored": restored, "file": name,
                "safety_backup": safety_path}
    finally:
        try:
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass
