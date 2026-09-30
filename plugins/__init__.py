"""Community plugins — drop a .py file here and it loads on boot.

Every file (except _-prefixed ones and this __init__) must contain at
least one @register skill. Files are safety-checked with the same
validator as auto-generated skills: limited imports, no eval/exec,
no subprocess, no file writes outside the file's own needs.

See _template.py for the minimal shape and README.md for the guide.
"""
from __future__ import annotations
import importlib
import pkgutil
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_loaded: list = []
_failed: list = []


def _validate_file(path: Path) -> dict:
    from skills.auto_generator import _validate
    return _validate(path.read_text(encoding="utf-8"))


def load_plugins() -> dict:
    """Import every valid plugin file. Safe to call repeatedly —
    already-loaded modules are skipped, new files get picked up.
    (Changed files need a server restart: Python can't unload.)"""
    global _loaded, _failed
    try:
        import plugins as _pkg
        search_path = _pkg.__path__
        prefix = _pkg.__name__ + "."
    except Exception as exc:
        log.warning("plugins: package resolve failed: %s", exc)
        return {"loaded": list(_loaded), "failed": list(_failed)}
    for mod in pkgutil.iter_modules(search_path):
        name = mod.name
        if name.startswith("_"):
            continue
        full = prefix + name
        if full in _loaded:
            continue
        if any(f["file"] == name for f in _failed):
            continue
        try:
            path = Path(search_path[0]) / f"{name}.py"
            meta = _validate_file(path)
            importlib.import_module(full)
            _loaded.append(full)
            log.info("plugin loaded: %s (%s)", name, meta["name"])
        except Exception as exc:
            reason = str(exc)[:160]
            _failed.append({"file": name, "error": reason})
            log.warning("plugin rejected %s: %s", name, reason)
    return {"loaded": list(_loaded), "failed": list(_failed)}


def status() -> dict:
    from skills.registry import all_skills
    return {
        "loaded": list(_loaded),
        "failed": list(_failed),
        "skill_count": len(all_skills()),
    }


load_plugins()
