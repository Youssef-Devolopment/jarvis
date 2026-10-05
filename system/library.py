"""One-click library: bundled skill packs + curated MCP servers.

Everything ships in the repo under ``library/``:

* ``library/catalog.json`` — the catalog (skill packs + MCP entries)
* ``library/skills/*.py``  — pack sources, installed on demand

Skill packs go through the SAME validator as community plugins
(``skills.auto_generator._validate``) and hot-load with no restart.
MCP entries reuse ``mcp.manager`` (add) + ``mcp.runtime`` (start);
``{HOME}``/``{DOCUMENTS}``/``{DESKTOP}`` placeholders expand so
one click produces a working server config.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_CATALOG = _ROOT / "library" / "catalog.json"
_PACKS = _ROOT / "library" / "skills"

_PLACEHOLDERS = {
    "{HOME}": str(Path.home()),
    "{DOCUMENTS}": str(Path.home() / "Documents"),
    "{DESKTOP}": str(Path.home() / "Desktop"),
}


def _expand(value):
    """Expand placeholders in a string or list of strings."""
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, str):
        for key, repl in _PLACEHOLDERS.items():
            value = value.replace(key, repl)
    return value


def load_catalog() -> dict:
    """Read + shape-validate the catalog. Never raises."""
    try:
        raw = json.loads(_CATALOG.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("library catalog unreadable: %s", exc)
        return {"skills": [], "mcp": []}
    skills = [e for e in (raw.get("skills") or [])
              if isinstance(e, dict) and e.get("id") and e.get("file")]
    mcps = [e for e in (raw.get("mcp") or [])
            if isinstance(e, dict) and e.get("id") and e.get("command")
            and e.get("name")]
    return {"skills": skills, "mcp": mcps}


def _pack_skill_names(entry: dict) -> list:
    """@register names declared inside the pack source."""
    try:
        src = (_PACKS / entry["file"]).read_text(encoding="utf-8")
    except Exception:
        return []
    return re.findall(r'@register\(\s*"([a-z0-9_]+)"', src)


def catalog() -> dict:
    """Catalog with installed flags — one payload for the UI."""
    cat = load_catalog()
    try:
        from skills.registry import all_skills
        have_skills = {s.name for s in all_skills()}
    except Exception:
        have_skills = set()
    try:
        from mcp.manager import all_servers
        have_mcp = {s.get("name") for s in all_servers()}
    except Exception:
        have_mcp = set()
    skills = []
    for e in cat["skills"]:
        names = _pack_skill_names(e)
        skills.append({**e,
                       "skills": names,
                       "installed": bool(names)
                       and all(n in have_skills for n in names)})
    mcps = [{**e, "installed": e.get("name") in have_mcp}
            for e in cat["mcp"]]
    return {"skills": skills, "mcp": mcps}


def install_skill_pack(pid: str) -> dict:
    """One click: bundled pack -> validated plugin -> hot-load."""
    entry = next((e for e in load_catalog()["skills"]
                  if e["id"] == pid), None)
    if not entry:
        return {"error": f"unknown skill pack: {pid}"}
    try:
        code = (_PACKS / entry["file"]).read_text(encoding="utf-8")
    except Exception as exc:
        return {"error": f"pack file missing: {exc}"}
    from plugins import install_plugin
    res = install_plugin(entry["id"], code)
    if res.get("error"):
        return res
    log.info("library: skill pack %s installed", pid)
    return {"ok": True, "pack": entry["id"],
            "skill": res.get("skill") or entry["id"],
            "name": entry.get("name", entry["id"])}


def _set_env(sid: str, env: dict) -> None:
    """Attach env vars to an installed server (same pattern as
    presets.install_preset)."""
    from mcp import manager
    with manager._lock:
        items = manager._load()
        for s in items:
            if s.get("id") == sid:
                s["env"] = dict(env)
        manager._save(items)


def add_mcp_entry(pid: str, start: bool = True) -> dict:
    """One click: add a catalog MCP server (+ best-effort start)."""
    entry = next((e for e in load_catalog()["mcp"]
                  if e["id"] == pid), None)
    if not entry:
        return {"error": f"unknown mcp entry: {pid}"}
    from mcp import manager
    name = entry["name"]
    existing = next((s for s in manager.all_servers()
                     if s.get("name") == name), None)
    if existing:
        server, added = existing, False
    else:
        server = manager.add_server(name, entry["command"],
                                    _expand(entry.get("args") or []))
        if not isinstance(server, dict) or server.get("error"):
            return {"error": (server.get("error")
                              if isinstance(server, dict)
                              else "add failed")}
        env = {k: str(v) for k, v in (entry.get("env") or {}).items()}
        if env:
            _set_env(server.get("id"), env)
            server["env"] = env
        added = True

    started, note = None, ""
    needs_key = bool(entry.get("env")) and any(
        not str(v).strip() for v in (entry.get("env") or {}).values())
    if start and entry.get("auto_start", True) and not needs_key:
        try:
            from mcp import runtime
            ok = runtime.start_server(name)
            started = bool(ok)
            if not ok:
                note = "added, but start failed — check the MCP tab/logs"
        except Exception as exc:
            note = f"added; start error: {str(exc)[:100]}"
    elif needs_key:
        note = ("added — set the API key in the entry's env, "
                "then press START in the MCP tab")
    log.info("library: mcp %s %s", name,
             "added" if added else "already present")
    return {"ok": True, "added": added, "server": server,
            "started": started, "note": note, "needs_key": needs_key}
