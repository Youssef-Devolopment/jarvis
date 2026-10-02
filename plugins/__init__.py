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


def install_plugin(name: str, code: str) -> dict:
    """One-click plugin install: validate → save → load. No restart."""
    import re as _re
    name = (name or "").strip().lower()
    if not _re.fullmatch(r"[a-z][a-z0-9_]{1,30}", name):
        return {"error": f"bad plugin name: {name!r}"}
    try:
        from skills.auto_generator import _validate
        meta = _validate(code)
    except Exception as exc:
        return {"error": f"validation failed: {exc}"}
    try:
        import plugins as _pkg
        dest = Path(_pkg.__path__[0]) / f"{name}.py"
    except Exception as exc:
        return {"error": f"plugin dir missing: {exc}"}
    if dest.exists():
        return {"error": f"plugin '{name}' already exists"}
    try:
        dest.write_text(code, encoding="utf-8")
    except Exception as exc:
        return {"error": f"write failed: {exc}"}
    full = f"plugins.{name}"
    try:
        importlib.import_module(full)
        _loaded.append(full)
    except Exception as exc:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return {"error": f"load failed: {str(exc)[:160]}"}
    log.info("plugin installed: %s (%s)", name, meta["name"])
    return {"ok": True, "file": name, "skill": meta["name"]}


load_plugins()
