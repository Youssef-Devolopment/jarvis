"""Read-only access to JARVIS own code."""
from __future__ import annotations
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)
_ROOT = Path(__file__).resolve().parent.parent

_ALLOWED_DIRS = {"ai", "skills", "voice", "routes", "moods", "memory", "harness",
                 "system", "plugins", "static", "templates"}
_ALLOWED_FILES = {"config.py", "logger.py", "errors.py", "server.py", "run.py"}


def _safe_path(rel: str):
    p = (_ROOT / rel).resolve()
    try:
        p.relative_to(_ROOT)
    except ValueError:
        return None
    top = p.relative_to(_ROOT).parts[0] if p != _ROOT else ""
    if top in _ALLOWED_DIRS or (len(p.relative_to(_ROOT).parts) == 1 and top in _ALLOWED_FILES):
        return p
    return None


def read_file(rel: str, max_bytes: int = 200_000) -> str:
    p = _safe_path(rel)
    if p is None or not p.exists() or p.is_dir():
        return f"[harness] Not allowed or missing: {rel}"
    data = p.read_bytes()[:max_bytes]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return f"[harness] Binary file: {rel}"


def list_files() -> list[str]:
    out = []
    for name in _ALLOWED_FILES:
        if (_ROOT / name).exists():
            out.append(name)
    for d in _ALLOWED_DIRS:
        dp = _ROOT / d
        if dp.is_dir():
            for f in sorted(dp.glob("*.py")):
                out.append(f"{d}/{f.name}")
    return sorted(out)


def search(query: str, limit: int = 20) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    results = []
    for rel in list_files():
        try:
            text = read_file(rel)
            for i, line in enumerate(text.splitlines(), 1):
                if q.lower() in line.lower():
                    results.append({"file": rel, "line": i, "text": line[:200]})
                    if len(results) >= limit:
                        return results
        except Exception:
            continue
    return results
