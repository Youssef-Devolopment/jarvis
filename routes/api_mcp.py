"""routes.api_mcp — MCP servers: list, presets, add/start/stop."""
from routes._common import (
    ValidationError,
    bp,
    jsonify,
    mcp_add,
    mcp_list,
    request,
)


# ---------- MCP ----------
@bp.get("/mcp")
def mcp_all():
    return jsonify({"servers": mcp_list()})


@bp.post("/mcp/preset")
def mcp_preset_install():
    from mcp import presets
    d = request.get_json(silent=True) or {}
    pid = (d.get("preset") or "").strip()
    if not pid:
        raise ValidationError("Missing 'preset'.")
    r = presets.install_preset(pid, args=d.get("args", "") or "",
                               env=d.get("env") or None)
    if r.get("error"):
        raise ValidationError(r["error"])
    return jsonify(r)


@bp.post("/mcp")
def mcp_add_route():
    d = request.get_json(silent=True) or {}
    r = mcp_add(
        d.get("name", ""),
        d.get("command", ""),
        d.get("args", ""),
        bool(d.get("enabled", True)),
    )
    if "error" in r:
        raise ValidationError(r["error"])
    return jsonify({"ok": True, "server": r})


@bp.post("/mcp/start")
def mcp_start_route():
    from mcp import runtime
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        # Start all
        result = runtime.start_all()
        return jsonify({"ok": True, **result})
    ok = runtime.start_server(name)
    return jsonify({"ok": ok, "server": name})


@bp.post("/mcp/stop")
def mcp_stop_route():
    """Body: {"name": optional} — stop one server, or all when omitted."""
    from mcp import runtime
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if name:
        return jsonify({"ok": runtime.stop_server(name), "server": name})
    runtime.shutdown_all()
    return jsonify({"ok": True})


