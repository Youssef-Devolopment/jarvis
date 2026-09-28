"""List & select OpenCode models via CLI."""

from __future__ import annotations
import os
import re
import shutil
import subprocess
from typing import Optional
from logger import get_logger

log = get_logger(__name__)


def _exe() -> Optional[str]:
    for name in ("opencode.cmd", "opencode.exe", "opencode"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _hidden() -> dict:
    kw = {"stdout": subprocess.PIPE, "stderr": subprocess.PIPE,
          "stdin": subprocess.DEVNULL, "text": True,
          "encoding": "utf-8", "errors": "replace"}
    if os.name == "nt":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def list_models() -> list[dict]:
    """Run `opencode models` and parse the output."""
    exe = _exe()
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "models"], timeout=20, **_hidden())
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        models = []
        seen = set()
        # Format is usually: provider/model-id  (maybe extra columns)
        for line in out.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("--"):
                continue
            m = re.match(r"^([\w\-]+)/([\w\-\.:]+)", line)
            if not m:
                continue
            provider, name = m.group(1), m.group(2)
            full = f"{provider}/{name}"
            if full in seen:
                continue
            seen.add(full)
            models.append({
                "id": full,
                "provider": provider,
                "name": name,
                "display": name.replace("-", " ").replace("_", " ").title(),
            })
        log.info("Found %d OpenCode models", len(models))
        return models
    except Exception as exc:
        log.exception("Failed to list models: %s", exc)
        return []


def get_active_model() -> str:
    """Read active model from prefs."""
    try:
        from memory import get_pref
        return get_pref("opencode_model", "") or ""
    except Exception:
        return ""


def set_active_model(model_id: str) -> bool:
    try:
        from memory import set_pref
        return set_pref("opencode_model", model_id)
    except Exception:
        return False
