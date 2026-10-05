"""Self-cleaning: old temp files + stale dream reports.

Two-step by design (matches "approve to fix it"): scan/report first,
delete only on explicit confirm — voice ("tidy confirm"), API, or the
nightly Dream run (pref-gated, user must be idle anyway).
"""
from __future__ import annotations
import os
import time
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

MAX_AGE_DAYS = 7
MAX_FILES = 5000
MAX_SECONDS = 60
KEEP_DREAM_REPORTS = 30


def _temp_dirs() -> list[Path]:
    out = []
    for var in ("TEMP", "TMP"):
        v = os.environ.get(var, "")
        if v:
            p = Path(v)
            if p.is_dir() and p not in out:
                out.append(p)
    windir = os.environ.get("SystemRoot", r"C:\Windows")
    wt = Path(windir) / "Temp"
    try:
        if wt.is_dir():
            out.append(wt)
    except Exception:
        pass
    return out


def scan(max_age_days: int = MAX_AGE_DAYS) -> dict:
    """Walk temp dirs. Pure read — never deletes. Capped for speed."""
    cutoff = time.time() - max_age_days * 86400
    t0 = time.time()
    files: list[str] = []
    total = 0
    scanned = 0
    for root in _temp_dirs():
        try:
            stack = [root]
            while stack:
                if (len(files) >= MAX_FILES
                        or time.time() - t0 > MAX_SECONDS):
                    break
                cur = stack.pop()
                try:
                    with os.scandir(cur) as it:
                        entries = list(it)
                except Exception:
                    continue
                for e in entries:
                    try:
                        if e.is_dir(follow_symlinks=False):
                            stack.append(Path(e.path))
                        elif e.is_file(follow_symlinks=False):
                            scanned += 1
                            try:
                                if e.stat().st_mtime < cutoff:
                                    files.append(e.path)
                                    total += e.stat().st_size
                            except Exception:
                                continue
                    except Exception:
                        continue
        except Exception:
            continue
    return {"dirs": [str(d) for d in _temp_dirs()], "scanned": scanned,
            "stale_files": len(files), "stale_mb": round(total / 1048576, 1),
            "paths": files}


def clean(dry_run: bool = True,
          max_age_days: int = MAX_AGE_DAYS) -> dict:
    """Delete stale temp files (dry_run only reports). In-use/locked
    files are skipped, never forced. Returns a report dict."""
    found = scan(max_age_days)
    removed, reclaimed, errors = 0, 0, 0
    if not dry_run:
        for fp in found["paths"]:
            try:
                st = os.stat(fp)
                os.remove(fp)
                removed += 1
                reclaimed += st.st_size
            except Exception:
                errors += 1
    return {"scanned": found["scanned"],
            "stale_files": found["stale_files"],
            "stale_mb": found["stale_mb"],
            "removed": removed,
            "reclaimed_mb": round(reclaimed / 1048576, 1),
            "skipped_errors": errors,
            "voice_pruned": (prune_voice_cache()["pruned"]
                             if not dry_run else 0),
            "dry_run": dry_run}


def prune_voice_cache(keep: int = 50,
                      cache_dir: Path | None = None) -> dict:
    """LRU-cap the TTS voice cache. Files are pure regenerable cache
    (voice/output.py re-creates on miss) — safe to drop oldest."""
    from pathlib import Path as _P
    root = _P(cache_dir) if cache_dir else _P(
        __file__).resolve().parent.parent / ".voice_cache"
    try:
        files = [p for p in root.iterdir()
                 if p.is_file() and p.suffix.lower() in
                 (".mp3", ".wav", ".tmp")]
    except Exception:
        return {"pruned": 0}
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    pruned, freed = 0, 0
    for old in files[keep:]:
        try:
            freed += old.stat().st_size
            old.unlink()
            pruned += 1
        except Exception:
            continue
    return {"pruned": pruned, "freed_mb": round(freed / 1048576, 1)}


def prune_dream_reports(keep: int = KEEP_DREAM_REPORTS) -> dict:
    """Drop old dream report JSONs, keep newest N. Own dir, safe."""
    try:
        from ai import dream_mode
        rep = Path(dream_mode._REPORTS)
    except Exception:
        return {"pruned": 0}
    try:
        files = sorted(rep.glob("dream_*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
    except Exception:
        return {"pruned": 0}
    pruned = 0
    for old in files[keep:]:
        try:
            old.unlink()
            pruned += 1
        except Exception:
            continue
    return {"pruned": pruned}
