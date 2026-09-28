"""Approved auto-generated skills. Each file registers itself on import.

Files land here ONLY via skills.auto_generator.approve_skill() after
explicit user approval. Nothing in this folder is hand-written.
"""
from __future__ import annotations
import pkgutil
from logger import get_logger

log = get_logger(__name__)

_loaded = []
for _mod in pkgutil.iter_modules(__path__):
    try:
        __import__(f"{__name__}.{_mod.name}")
        _loaded.append(_mod.name)
    except Exception as exc:
        log.warning("auto_generated: skipping %s (%s)", _mod.name, exc)
if _loaded:
    log.info("auto_generated skills loaded: %s", ", ".join(_loaded))
