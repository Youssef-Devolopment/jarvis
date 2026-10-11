"""Module ecosystem — JARVIS's real extensibility framework.

A module is a folder under ``modules/`` with a ``module.json`` manifest.
Two kinds ship today:

* ``skill`` — a ``skill.py`` entry that registers @register skills,
  validated with the SAME AST safety rules + hijack guards as
  community plugins (limited imports, no eval/exec/open/subprocess);
* ``mcp``   — an MCP server spec (command/args/env) that is wired into
  ``mcp.manager`` / ``mcp.runtime`` on activation.

Every module DECLARES what it does before it may run: capabilities,
permissions (a fixed, reviewable vocabulary), docs (README) and
examples — so the MODULES tab can show users exactly what they are
granting BEFORE anything is activated.

Trust rules (all enforced, all tested):
  - manifests are schema-validated; unknown permissions, bad ids and
    shell metacharacters in commands are rejected with reasons,
  - skill entries pass ``skills.auto_generator._validate`` before the
    file is ever imported,
  - zip installs refuse traversal (zip-slip), absolute paths and
    oversized archives,
  - a module that fails validation or activation is surfaced as
    ``failed`` with its error — never silently ignored,
  - nothing loads by itself: install/activate writes
    ``modules/state.json`` and boot only re-activates what you enabled.

Lifecycle: validate (dry run) -> install (folder or .zip) -> activate
/ deactivate -> uninstall. Update status compares the manifest version
against the bundled ``modules/catalog.json`` snapshot — the same shape
a future remote registry will publish.
"""
from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

from logger import get_logger

log = get_logger(__name__)

SCHEMA = 1                       # manifest schema this build understands
MANIFEST_NAME = "module.json"

_ROOT = Path(__file__).resolve().parent.parent / "modules"
_STATE = _ROOT / "state.json"          # runtime state (gitignored)
_CATALOG = _ROOT / "catalog.json"      # bundled version snapshot

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
_SRV_RE = re.compile(r"^[a-z][a-z0-9_\-]{0,29}$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_CMD_RE = re.compile(r"^[A-Za-z0-9._\-:\\/]+$")

_MAX_FILES = 200
_MAX_SINGLE = 2 * 1024 * 1024          # 2 MB per file
_MAX_TOTAL = 10 * 1024 * 1024          # 10 MB uncompressed per zip
_ALLOWED_SUFFIXES = {".py", ".json", ".md", ".txt", ".toml", ".cfg", ".ini"}
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}

# What a module may ask for. Everything outside this vocabulary is
# rejected — the point is a small, reviewable permission surface.
PERMISSIONS = {
    "none": "Pure computation — only sees the words you type.",
    "read:text": "Reads text you provide in the command.",
    "read:file": "Reads files on disk.",
    "write:file": "Writes files on disk.",
    "network": "Makes outbound network requests.",
    "process": "Launches other programs.",
    "memory": "Reads or writes JARVIS memory and notes.",
    "clipboard": "Touches the clipboard.",
    "registry": "Touches Windows registry or app config.",
}

_PLACEHOLDERS = {
    "{HOME}": str(Path.home()),
    "{DOCUMENTS}": str(Path.home() / "Documents"),
    "{DESKTOP}": str(Path.home() / "Desktop"),
}


class ModuleError(ValueError):
    """A module was rejected, is missing, or failed to load.
    The message is plain English and shown to the user as-is."""


# ---------------------------------------------------------------- state
def _load_state() -> dict:
    try:
        raw = json.loads(_STATE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def _save_state(st: dict) -> None:
    try:
        _STATE.parent.mkdir(parents=True, exist_ok=True)
        _STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")
    except Exception as exc:
        log.warning("modules: state save failed: %s", exc)


def _mark_failed(module_id: str, msg: str) -> None:
    st = _load_state()
    rec = st.get(module_id) or {"enabled": False, "source": "local"}
    rec.update({"enabled": False, "error": str(msg)[:200]})
    st[module_id] = rec
    _save_state(st)


def _catalog_versions() -> dict:
    """Bundled {id: latest_version} snapshot (future: remote registry)."""
    try:
        raw = json.loads(_CATALOG.read_text(encoding="utf-8"))
        mods = raw.get("modules") or {}
        return {k: str(v) for k, v in mods.items() if isinstance(v, str)}
    except Exception:
        return {}


def _semver_tuple(v: str):
    try:
        return tuple(int(x) for x in str(v).split("."))
    except Exception:
        return (0, 0, 0)


def _update_info(mid: str, version: str, latest_map: dict) -> dict:
    latest = latest_map.get(mid)
    if not latest:
        return {"available": False, "latest": None}
    return {"available": _semver_tuple(latest) > _semver_tuple(version),
            "latest": latest}


def _expand(value):
    """Expand {HOME}/{DOCUMENTS}/{DESKTOP} in a string or list."""
    if isinstance(value, list):
        return [_expand(v) for v in value]
    if isinstance(value, str):
        for key, repl in _PLACEHOLDERS.items():
            value = value.replace(key, repl)
    return value


# ------------------------------------------------------------ validation
def validate_manifest(d: dict) -> dict:
    """Schema-check one module.json object. Returns a normalized copy.
    Raises ModuleError with a plain-English reason on any violation."""
    if not isinstance(d, dict):
        raise ModuleError("manifest must be a JSON object")
    m = dict(d)
    schema = m.get("schema", SCHEMA)
    if not isinstance(schema, int) or schema > SCHEMA:
        raise ModuleError(f"unsupported manifest schema {schema!r} "
                          f"(this build understands {SCHEMA})")
    mid = str(m.get("id") or "")
    if not _ID_RE.fullmatch(mid):
        raise ModuleError("manifest 'id' must be lowercase letters, digits "
                          "and underscores (max 30 chars)")
    name = str(m.get("name") or "").strip()
    if not name or len(name) > 60:
        raise ModuleError("manifest 'name' must be 1-60 characters")
    version = str(m.get("version") or "")
    if not _SEMVER_RE.fullmatch(version):
        raise ModuleError("manifest 'version' must look like 1.2.3")
    desc = str(m.get("description") or "").strip()
    if not desc or len(desc) > 300:
        raise ModuleError("manifest 'description' must be 1-300 characters")

    entry = m.get("entry")
    mcp_spec = m.get("mcp")
    kind = str(m.get("kind") or "").strip().lower()
    if not kind:
        kind = "mcp" if mcp_spec else "skill"
    if kind not in ("skill", "mcp"):
        raise ModuleError("manifest 'kind' must be 'skill' or 'mcp'")
    if kind == "skill":
        if not entry or not isinstance(entry, str):
            raise ModuleError("skill modules need an 'entry' python file")
        if "/" in entry or "\\" in entry or ".." in entry:
            raise ModuleError("'entry' must be a plain file name inside "
                              "the module folder")
    else:
        if not isinstance(mcp_spec, dict) or not mcp_spec.get("command"):
            raise ModuleError("mcp modules need an 'mcp' block with a "
                              "'command'")
        if not _SRV_RE.fullmatch(str(mcp_spec.get("name") or "")):
            raise ModuleError("mcp 'name' must be lowercase letters, "
                              "digits, underscores or dashes")
        cmd = str(mcp_spec["command"]).strip()
        if not _CMD_RE.fullmatch(cmd):
            raise ModuleError("mcp 'command' contains unsafe characters")
        args = mcp_spec.get("args") or []
        if (not isinstance(args, list) or len(args) > 20
                or not all(isinstance(a, str) for a in args)):
            raise ModuleError("mcp 'args' must be a list of up to 20 "
                              "strings")
        env = mcp_spec.get("env") or {}
        if not isinstance(env, dict) or not all(
                isinstance(k, str) and isinstance(v, str)
                for k, v in env.items()):
            raise ModuleError("mcp 'env' must map strings to strings")

    perms = m.get("permissions") or ["none"]
    if not isinstance(perms, list) or not perms:
        raise ModuleError("'permissions' must be a non-empty list")
    for p in perms:
        if p not in PERMISSIONS:
            raise ModuleError(f"unknown permission {p!r} — allowed: "
                              + ", ".join(sorted(PERMISSIONS)))
    if "none" in perms and len(perms) > 1:
        raise ModuleError("'none' cannot be combined with other permissions")
    caps = m.get("capabilities") or []
    if (not isinstance(caps, list) or not (1 <= len(caps) <= 8)
            or not all(isinstance(c, str) and c.strip() for c in caps)):
        raise ModuleError("'capabilities' must list 1-8 short strings")
    examples = m.get("examples") or []
    if not isinstance(examples, list) or len(examples) > 5:
        raise ModuleError("'examples' must be a list of up to 5 objects")
    for ex in examples:
        if not isinstance(ex, dict) or not str(ex.get("phrase") or "").strip():
            raise ModuleError("each example needs a 'phrase'")

    m.update({"kind": kind, "name": name, "version": version,
              "description": desc, "permissions": list(perms),
              "capabilities": [c.strip() for c in caps],
              "examples": examples})
    return m


def _validate_entry_code(path: Path) -> dict:
    """Skill entries pass the SAME validator as community plugins:
    limited imports, no eval/exec/open/subprocess, hijack-proof
    patterns. Raises ValueError with the reason."""
    from skills.auto_generator import _validate
    return _validate(path.read_text(encoding="utf-8"))


def validate_module_dir(path, check_name: bool = True) -> dict:
    """Validate a module folder (manifest + entry code + docs).
    check_name enforces "folder name == manifest id" — true for
    folders living under modules/, false when validating an outside
    folder or zip before install (the copy lands in modules/<id>).
    Returns {"manifest": dict, "warnings": [str]}; raises ModuleError."""
    p = Path(path)
    if not p.is_dir():
        raise ModuleError(f"not a folder: {p}")
    mf = p / MANIFEST_NAME
    if not mf.is_file():
        raise ModuleError(f"no {MANIFEST_NAME} in '{p.name}' — every "
                          "module folder needs one")
    try:
        raw = json.loads(mf.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ModuleError(f"{MANIFEST_NAME} is not valid JSON: {exc}")
    m = validate_manifest(raw)
    if check_name and m["id"] != p.name:
        raise ModuleError(f"manifest id '{m['id']}' must match the folder "
                          f"name '{p.name}'")
    warnings = []
    if m["kind"] == "skill":
        entry = p / m["entry"]
        if not entry.is_file():
            raise ModuleError(f"entry file missing: {m['entry']}")
        try:
            _validate_entry_code(entry)
        except ValueError as exc:
            raise ModuleError(f"entry code rejected: {exc}")
        for n in (m.get("skills") or []):
            if not _ID_RE.fullmatch(str(n)):
                raise ModuleError(f"declared skill name {n!r} is not a "
                                  "valid skill name")
    docs = m.get("docs") or "README.md"
    if not (p / docs).is_file():
        warnings.append(f"no docs file ({docs}) — users won't be able to "
                        "review this module")
    if not m.get("examples"):
        warnings.append("no examples declared")
    return {"manifest": m, "warnings": warnings}


# ------------------------------------------------------------- inventory
def _entry_view(m: dict, rec: dict, path: Path, latest_map: dict) -> dict:
    state = ("failed" if rec.get("error")
             else "active" if rec.get("enabled") else "inactive")
    v = {"id": m["id"], "name": m["name"], "version": m["version"],
         "kind": m["kind"], "author": m.get("author", ""),
         "description": m["description"], "state": state,
         "error": rec.get("error"), "enabled": bool(rec.get("enabled")),
         "capabilities": m["capabilities"],
         "permissions": m["permissions"], "examples": m["examples"],
         "source": rec.get("source", "shipped"),
         "skills": rec.get("skills") or [],
         "update": _update_info(m["id"], m["version"], latest_map)}
    docs = m.get("docs") or "README.md"
    v["docs"] = docs if (path / docs).is_file() else None
    if m["kind"] == "mcp":
        spec = m["mcp"]
        env = spec.get("env") or {}
        v["needs_key"] = bool(env) and any(
            not str(x).strip() for x in env.values())
        v["running"] = _mcp_running(spec["name"])
    return v


def _mcp_running(name: str) -> bool:
    try:
        from mcp import runtime
        return bool(runtime.is_running(name))
    except Exception:
        return False


def scan() -> list:
    """Every installed module with its live state. Never raises —
    a broken folder comes back as state 'failed' with its error."""
    st = _load_state()
    latest_map = _catalog_versions()
    out = []
    if not _ROOT.is_dir():
        return out
    changed = False
    for child in sorted(_ROOT.iterdir()):
        if not child.is_dir() or child.name.startswith(("_", ".")):
            continue          # templates (_template_*) and junk skipped
        try:
            res = validate_module_dir(child)
            m = res["manifest"]
        except ModuleError as exc:
            out.append({"id": child.name, "name": child.name, "kind": "?",
                        "state": "failed", "error": str(exc),
                        "capabilities": [], "permissions": [],
                        "examples": [], "enabled": False,
                        "source": "shipped", "update": {"available": False,
                                                        "latest": None}})
            continue
        if child.name not in st:      # first sight: ship enabled by default
            st[child.name] = {"enabled": True, "error": None,
                              "source": "shipped"}
            changed = True
        v = _entry_view(m, st[child.name], child, latest_map)
        v["warnings"] = res["warnings"]
        out.append(v)
    if changed:
        _save_state(st)
    return out


def detail(module_id: str) -> dict:
    """Full module view for the UI: state + docs text + mcp spec."""
    path = _ROOT / module_id
    if not path.is_dir():
        raise ModuleError(f"module not installed: {module_id}")
    res = validate_module_dir(path)
    m = res["manifest"]
    rec = _load_state().get(module_id) or {}
    v = _entry_view(m, rec, path, _catalog_versions())
    v["warnings"] = res["warnings"]
    v["entry"] = m.get("entry")
    docs = m.get("docs") or "README.md"
    f = path / docs
    v["docs_text"] = f.read_text(encoding="utf-8") if f.is_file() else ""
    if m["kind"] == "mcp":
        spec = m["mcp"]
        v["mcp"] = {"name": spec["name"], "command": spec["command"],
                    "args": _expand(spec.get("args") or []),
                    "auto_start": bool(spec.get("auto_start", True)),
                    "env_keys": sorted((spec.get("env") or {}).keys())}
    return v


# -------------------------------------------------------------- lifecycle
def _is_live(module_id: str, m: dict) -> bool:
    """Is this module already loaded in THIS process?"""
    if m["kind"] == "skill":
        return f"jarvis_module_{module_id}" in sys.modules
    try:
        from mcp import manager
        name = m["mcp"]["name"]
        return any(s.get("name") == name for s in manager.all_servers())
    except Exception:
        return False


def _activate_skill(module_id: str, path: Path, m: dict) -> dict:
    """Validate + import the entry file; returns registered skill names.
    Rolls back completely if anything goes wrong."""
    from skills import registry
    entry = path / m["entry"]
    try:
        code = entry.read_text(encoding="utf-8")
    except Exception as exc:
        raise ModuleError(f"entry file unreadable: {exc}")
    try:
        _validate_entry_code(entry)
    except ValueError as exc:
        raise ModuleError(f"entry code rejected: {exc}")
    before = {s.name for s in registry.all_skills()}
    modname = f"jarvis_module_{module_id}"
    spec = importlib.util.spec_from_file_location(modname, entry)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        # A crash mid-import can leave skills behind — roll them back
        # so a failed module never half-registers.
        after = {s.name for s in registry.all_skills()}
        for n in (after - before):
            registry.unregister(n)
        sys.modules.pop(modname, None)
        raise ModuleError(f"module crashed on load: {str(exc)[:160]}")
    after = {s.name for s in registry.all_skills()}
    names = sorted(after - before)
    decl = set(m.get("skills") or [])
    if decl and (decl - set(names)):
        for n in names:                       # rollback: full unregister
            registry.unregister(n)
        sys.modules.pop(modname, None)
        raise ModuleError(
            "declared skills did not register: "
            + ", ".join(sorted(decl - set(names))))
    if not names:
        sys.modules.pop(modname, None)
        raise ModuleError("entry loaded but registered no skills")
    return {"skills": names}


def _activate_mcp(module_id: str, path: Path, m: dict) -> dict:
    """Wire the declared MCP server into mcp.manager (+ best-effort
    start). An existing entry with the same name is reused as-is."""
    from mcp import manager
    spec = m["mcp"]
    name = spec["name"]
    env = dict(spec.get("env") or {})
    needs_key = bool(env) and any(not str(v).strip() for v in env.values())
    existing = next((s for s in manager.all_servers()
                     if s.get("name") == name), None)
    if not existing:
        enabled = bool(spec.get("auto_start", True)) and not needs_key
        server = manager.add_server(name, spec["command"],
                                    _expand(spec.get("args") or []),
                                    enabled=enabled)
        if not isinstance(server, dict) or server.get("error"):
            reason = (server.get("error") if isinstance(server, dict)
                      else "could not write the server config")
            raise ModuleError(f"mcp config failed: {reason}")
        if env:
            _set_env(server.get("id"), env)
    started, note = None, ""
    if not needs_key and bool(spec.get("auto_start", True)):
        try:
            from mcp import runtime
            started = bool(runtime.start_server(name))
            if not started:
                note = "configured, but start failed — see the MCP tab"
        except Exception as exc:
            note = f"configured; start error: {str(exc)[:100]}"
    elif needs_key:
        note = "set its API key in the MCP tab, then press START"
    return {"server": name, "note": note, "needs_key": needs_key,
            "started": started}


def _set_env(sid: str, env: dict) -> None:
    """Attach env vars to the installed server entry (same pattern as
    system.library._set_env)."""
    from mcp import manager
    with manager._lock:
        items = manager._load()
        for s in items:
            if s.get("id") == sid:
                s["env"] = dict(env)
        manager._save(items)


def activate(module_id: str) -> dict:
    """Validate + load a module now. Idempotent. Raises ModuleError."""
    path = _ROOT / module_id
    st = _load_state()
    rec = st.get(module_id) or {"enabled": True, "error": None,
                                "source": "shipped"}
    if not path.is_dir():
        raise ModuleError(f"module not installed: {module_id}")
    m = validate_module_dir(path)["manifest"]
    if rec.get("enabled") and not rec.get("error") and _is_live(module_id, m):
        return {"ok": True, "id": module_id, "already": True,
                "state": "active", "skills": rec.get("skills") or []}
    try:
        if m["kind"] == "skill":
            extra = _activate_skill(module_id, path, m)
        else:
            extra = _activate_mcp(module_id, path, m)
    except ModuleError as exc:
        rec.update({"enabled": False, "error": str(exc)[:200]})
        st[module_id] = rec
        _save_state(st)
        raise
    rec.update({"enabled": True, "error": None})
    rec.update(extra)
    st[module_id] = rec
    _save_state(st)
    log.info("modules: %s activated (%s)", module_id, m["kind"])
    return {"ok": True, "id": module_id, "state": "active",
            "skills": rec.get("skills") or [], **extra}


def deactivate(module_id: str) -> dict:
    """Unload a module: unregister its skills / stop + drop its MCP
    server. Raises ModuleError when the module is not installed."""
    st = _load_state()
    rec = st.get(module_id) or {}
    path = _ROOT / module_id
    if module_id not in st and not path.is_dir():
        raise ModuleError(f"module not installed: {module_id}")
    unregistered = []
    try:
        from skills import registry
        for n in rec.get("skills") or []:
            try:
                if registry.unregister(n):
                    unregistered.append(n)
            except Exception as exc:
                log.warning("modules: unregister %s failed: %s", n, exc)
    except Exception as exc:
        log.warning("modules: skill teardown failed: %s", exc)
    sys.modules.pop(f"jarvis_module_{module_id}", None)
    srv_name = rec.get("server")
    if not srv_name and path.is_dir():
        try:
            srv_name = ((validate_module_dir(path)["manifest"]
                         .get("mcp") or {}).get("name"))
        except ModuleError:
            srv_name = None
    if srv_name:
        try:
            from mcp import runtime
            runtime.stop_server(srv_name)
        except Exception:
            pass
        try:
            from mcp import manager
            srv = next((s for s in manager.all_servers()
                        if s.get("name") == srv_name), None)
            if srv and srv.get("id"):
                manager.remove_server(srv["id"])
        except Exception as exc:
            log.warning("modules: mcp teardown failed: %s", exc)
    rec.update({"enabled": False, "error": None, "skills": [],
                "server": None})
    st[module_id] = rec
    _save_state(st)
    log.info("modules: %s deactivated (%d skills unregistered)",
             module_id, len(unregistered))
    return {"ok": True, "id": module_id, "state": "inactive",
            "unregistered": unregistered}


# ----------------------------------------------------------- install path
def _safe_extract(zpath: Path, dest: Path) -> None:
    """Extract a module zip with zip-slip / zip-bomb guards."""
    import zipfile
    try:
        z = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile:
        raise ModuleError("not a valid zip file")
    with z:
        infos = z.infolist()
        if len(infos) > _MAX_FILES:
            raise ModuleError(f"zip has too many files "
                              f"({len(infos)} > {_MAX_FILES})")
        total = 0
        for info in infos:
            name = info.filename
            if (name.startswith(("/", "\\")) or ".." in Path(name).parts
                    or (len(name) > 1 and name[1] == ":")):
                raise ModuleError(f"zip contains an unsafe path: {name}")
            total += info.file_size
            if total > _MAX_TOTAL:
                raise ModuleError("zip is too large (over 10 MB "
                                  "uncompressed)")
        dest.mkdir(parents=True, exist_ok=True)
        z.extractall(dest)


def _find_module_dir(dest: Path) -> Path:
    """Locate the folder holding module.json (root or one level deep)."""
    if (dest / MANIFEST_NAME).is_file():
        return dest
    for child in sorted(dest.iterdir()):
        if child.is_dir() and (child / MANIFEST_NAME).is_file():
            return child
    raise ModuleError("zip does not contain a module.json")


def _copy_module(src: Path, dst: Path) -> None:
    """Copy a validated module folder; enforces size/file limits."""
    files = [f for f in sorted(src.rglob("*"))
             if f.is_file() and not (_SKIP_DIRS & set(f.parts))]
    if len(files) > _MAX_FILES:
        raise ModuleError(f"too many files ({len(files)} > {_MAX_FILES})")
    total = 0
    for f in files:
        if f.suffix.lower() not in _ALLOWED_SUFFIXES:
            raise ModuleError(f"file type not allowed: {f.name} "
                              "(modules ship .py/.json/.md/.txt only)")
        total += f.stat().st_size
        if total > _MAX_TOTAL:
            raise ModuleError("module is too large (over 10 MB)")
    dst.mkdir(parents=True, exist_ok=False)
    for f in files:
        rel = f.relative_to(src)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)


def install(src, activate_now: bool = True) -> dict:
    """Install from a local folder or .zip — validated FIRST, so a
    rejected package leaves nothing behind. Raises ModuleError."""
    p = Path(str(src)).expanduser()
    if not p.exists():
        raise ModuleError(f"no such path: {p}")
    if p.is_dir():
        return _install_dir(p, activate_now)
    if p.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory() as td:
            dest = Path(td) / "unpacked"
            _safe_extract(p, dest)
            return _install_dir(_find_module_dir(dest), activate_now)
    raise ModuleError("install source must be a module folder or a .zip")


def _install_dir(src: Path, activate_now: bool) -> dict:
    res = validate_module_dir(src, check_name=False)  # raises before copy
    m = res["manifest"]
    dst = _ROOT / m["id"]
    if dst.exists():
        raise ModuleError(f"module '{m['id']}' is already installed — "
                          "uninstall it first")
    _copy_module(src, dst)
    st = _load_state()
    st[m["id"]] = {"enabled": False, "error": None, "source": "local"}
    _save_state(st)
    out = {"ok": True, "id": m["id"], "name": m["name"], "kind": m["kind"],
           "permissions": m["permissions"], "state": "inactive",
           "warnings": res["warnings"]}
    if activate_now:
        try:
            a = activate(m["id"])
        except ModuleError as exc:           # installed, but shown FAILED
            out["state"] = "failed"
            out["error"] = str(exc)[:200]
            return out
        out.update({"state": a.get("state", "active"),
                    "skills": a.get("skills"), "note": a.get("note")})
    log.info("modules: installed %s (%s) from %s",
             m["id"], m["kind"], src)
    return out


def uninstall(module_id: str) -> dict:
    """Deactivate + delete an installed module. Raises ModuleError
    when the module is not installed."""
    st = _load_state()
    path = _ROOT / module_id
    if module_id not in st and not path.is_dir():
        raise ModuleError(f"module not installed: {module_id}")
    try:
        deactivate(module_id)
    except ModuleError:
        pass
    deleted = False
    if path.is_dir() and path.parent == _ROOT and \
            not path.name.startswith(("_", ".")):
        shutil.rmtree(path, ignore_errors=True)
        deleted = not path.exists()
    st = _load_state()                       # deactivate re-wrote state
    st.pop(module_id, None)
    _save_state(st)
    log.info("modules: %s uninstalled (deleted=%s)", module_id, deleted)
    return {"ok": True, "id": module_id, "deleted": deleted}


def validate_path(src) -> dict:
    """Dry-run validation for the author workflow: check a folder or
    .zip WITHOUT installing. Returns a report; never raises."""
    p = Path(str(src)).expanduser()
    try:
        if not p.exists():
            raise ModuleError(f"no such path: {p}")
        if p.is_dir():
            res = validate_module_dir(p, check_name=False)
        elif p.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory() as td:
                dest = Path(td) / "unpacked"
                _safe_extract(p, dest)
                res = validate_module_dir(_find_module_dir(dest),
                                          check_name=False)
        else:
            raise ModuleError("path must be a module folder or a .zip")
    except ModuleError as exc:
        return {"ok": False, "error": str(exc)}
    m = res["manifest"]
    return {"ok": True, "id": m["id"], "name": m["name"],
            "version": m["version"], "kind": m["kind"],
            "author": m.get("author", ""), "description": m["description"],
            "permissions": m["permissions"],
            "capabilities": m["capabilities"], "examples": m["examples"],
            "warnings": res["warnings"]}


def boot_load() -> str:
    """Activate every enabled module. Wired as a boot service — one
    broken module degrades itself, never the boot."""
    active = failed = 0
    for m in scan():
        if m.get("state") == "failed":
            failed += 1
            continue
        if not m.get("enabled"):
            continue
        try:
            activate(m["id"])
            active += 1
        except Exception as exc:             # recorded, surfaced, skipped
            _mark_failed(m["id"], str(exc))
            failed += 1
    return f"{active} module(s) active" + (
        f", {failed} failed" if failed else "")
