"""routes.api_market — plugins, marketplace, universal add, library, modules, backup."""
from routes._common import (
    ValidationError,
    bp,
    jsonify,
    request,
)


# ---------- COMMUNITY PLUGINS ----------
@bp.get("/plugins")
def plugins_status():
    from plugins import status
    return jsonify(status())


@bp.post("/plugins/reload")
def plugins_reload():
    from plugins import load_plugins
    return jsonify(load_plugins())


@bp.post("/plugins/install")
def plugins_install():
    from plugins import install_plugin
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    code = d.get("code") or ""
    if not name or not code:
        raise ValidationError("Missing 'name' or 'code'.")
    r = install_plugin(name, code)
    if r.get("error"):
        raise ValidationError(r["error"])
    return jsonify(r)


# ---------- MARKETPLACE (unified catalog) ----------
@bp.get("/market")
def market_catalog():
    """One catalog for everything installable: skills, pending
    drafts, plugins, MCP presets/servers, pinned sites."""
    from mcp.manager import all_servers
    from mcp.presets import list_presets
    from plugins import status as plugins_status
    from skills import all_skills
    from skills import auto_generator as _ag
    from system import launch as L
    skills = []
    for s in all_skills():
        mod = getattr(getattr(s, "handler", None), "__module__", "") or ""
        if mod.startswith("plugins."):
            source = "plugin"
        elif "auto_generated" in mod:
            source = "learned"
        else:
            source = "builtin"
        skills.append({"name": s.name, "description": s.description or "",
                       "enabled": bool(s.enabled), "source": source})
    try:
        pending = [{"name": p.get("name"), "source": p.get("source", ""),
                    "test_ok": bool(p.get("test_ok"))}
                   for p in _ag.list_pending()]
    except Exception:
        pending = []
    try:
        sites = [{"name": n, "url": u}
                 for n, u in sorted(L.custom_sites().items())]
    except Exception:
        sites = []
    try:
        from system import backup as _b
        backups = _b.list_backups()
    except Exception:
        backups = []
    return jsonify({
        "skills": skills,
        "pending": pending,
        "plugins": plugins_status(),
        "mcp_presets": list_presets(),
        "mcp_servers": all_servers(),
        "sites": sites,
        "backups": backups,
    })


@bp.post("/sites/unpin")
def sites_unpin():
    from system import launch as L
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        raise ValidationError("Missing 'name'.")
    out = L.unpin_site(name)
    if out.startswith("No pinned"):
        raise ValidationError(out)
    return jsonify({"ok": True, "output": out})


# ---------- UNIVERSAL ADD (sites, MCP, apps, skills) ----------
@bp.post("/add")
def universal_add():
    """One endpoint for every addable thing. Body: {"text": ...}."""
    from system import adder
    d = request.get_json(silent=True) or {}
    text = (d.get("text") or "").strip()
    if not text:
        raise ValidationError("Missing 'text'.")
    out = adder.add(text)
    if out is None:
        return jsonify({"ok": False,
                        "error": "Not an add command."}), 404
    return jsonify({"ok": True, "output": out})


# ---------- BACKUP ----------
@bp.post("/backup")
def backup_now():
    from system import backup as _b
    res = _b.create_backup()
    code = 200 if res.get("ok") else 500
    return jsonify(res), code


@bp.get("/backups")
def backups_list():
    from system import backup as _b
    items = _b.list_backups()
    return jsonify({"count": len(items), "backups": items})


@bp.post("/backup/restore")
def backup_restore():
    """Preview without confirm, apply with confirm=true.
    Body: {"file": optional-name, "confirm": bool}"""
    from system import backup as _b
    d = request.get_json(silent=True) or {}
    res = _b.restore_backup(d.get("file"),
                            confirm=bool(d.get("confirm")))
    if res.get("needs_confirm"):
        return jsonify(res)
    code = 200 if res.get("ok") else 400
    return jsonify(res), code


# ---------- LIBRARY (one-click skill packs + MCP servers) ----------
@bp.get("/library")
def library_catalog():
    from system import library
    return jsonify(library.catalog())


@bp.post("/library/skill")
def library_skill_install():
    """One click: install a pack (hot-loads, no restart), or remove
    it with {"remove": true}. Body: {"id": str, "remove": bool}"""
    from system import library
    d = request.get_json(silent=True) or {}
    pid = (d.get("id") or "").strip()
    if not pid:
        raise ValidationError("Missing 'id'.")
    r = (library.uninstall_skill_pack(pid) if d.get("remove")
         else library.install_skill_pack(pid))
    if r.get("error"):
        raise ValidationError(r["error"])
    return jsonify(r)


@bp.post("/library/mcp")
def library_mcp_add():
    """One click: add a catalog MCP server (best-effort auto-start),
    or drop it with {"remove": true}.
    Body: {"id": str, "start": bool=true, "remove": bool=false}"""
    from system import library
    d = request.get_json(silent=True) or {}
    pid = (d.get("id") or "").strip()
    if not pid:
        raise ValidationError("Missing 'id'.")
    r = (library.remove_mcp_entry(pid) if d.get("remove")
         else library.add_mcp_entry(pid, start=bool(d.get("start", True))))
    if r.get("error"):
        raise ValidationError(r["error"])
    return jsonify(r)


@bp.post("/library/import")
def library_import():
    """Import user-authored packs (JSON). Body: a pack object, a
    list, or {"packs": [...]} — each needs id + code."""
    from system import library
    d = request.get_json(silent=True) or {}
    r = library.import_packs(d)
    if r.get("error"):
        raise ValidationError(r["error"])
    return jsonify(r)


# ---------- MODULES (skill/MCP extensibility ecosystem) ----------
@bp.get("/modules")
def modules_list():
    """Every installed module with state, permissions and capabilities."""
    from system import modules as modsys
    mods = modsys.scan()
    counts = {"total": len(mods), "active": 0, "inactive": 0, "failed": 0}
    for m in mods:
        key = m.get("state", "inactive")
        counts[key] = counts.get(key, 0) + 1
    return jsonify({"modules": mods, "counts": counts,
                    "permissions": modsys.PERMISSIONS,
                    "framework": modsys.SCHEMA})


@bp.get("/modules/<mid>")
def modules_detail(mid):
    """One module in full: state, docs text, expanded mcp spec."""
    from system import modules as modsys
    try:
        return jsonify(modsys.detail(mid))
    except modsys.ModuleError as exc:
        raise ValidationError("Module unavailable.", detail=str(exc))


@bp.post("/modules/toggle")
def modules_toggle():
    """Activate or deactivate a module. Body: {"id", "enabled"}"""
    from system import modules as modsys
    d = request.get_json(silent=True) or {}
    mid = (d.get("id") or "").strip()
    if not mid:
        raise ValidationError("Missing 'id'.", detail="Missing 'id'.")
    try:
        r = (modsys.activate(mid) if d.get("enabled", True)
             else modsys.deactivate(mid))
    except modsys.ModuleError as exc:
        raise ValidationError("Module rejected.", detail=str(exc))
    return jsonify(r)


@bp.post("/modules/install")
def modules_install():
    """Install from a local folder or .zip (validated first).
    Body: {"path", "activate": bool=true}"""
    from system import modules as modsys
    d = request.get_json(silent=True) or {}
    path = (d.get("path") or "").strip()
    if not path:
        raise ValidationError("Missing 'path'.",
                              detail="Missing 'path' — folder or .zip.")
    try:
        r = modsys.install(path, activate_now=bool(d.get("activate", True)))
    except modsys.ModuleError as exc:
        raise ValidationError("Install rejected.", detail=str(exc))
    return jsonify(r)


@bp.post("/modules/uninstall")
def modules_uninstall():
    """Deactivate + delete a module. Body: {"id"}"""
    from system import modules as modsys
    d = request.get_json(silent=True) or {}
    mid = (d.get("id") or "").strip()
    if not mid:
        raise ValidationError("Missing 'id'.", detail="Missing 'id'.")
    try:
        r = modsys.uninstall(mid)
    except modsys.ModuleError as exc:
        raise ValidationError("Uninstall failed.", detail=str(exc))
    return jsonify(r)


@bp.post("/modules/validate")
def modules_validate():
    """Dry-run validation for module authors. Body: {"path"}"""
    from system import modules as modsys
    d = request.get_json(silent=True) or {}
    path = (d.get("path") or "").strip()
    if not path:
        raise ValidationError("Missing 'path'.",
                              detail="Missing 'path' — folder or .zip.")
    return jsonify(modsys.validate_path(path))


