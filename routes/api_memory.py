"""routes.api_memory — memory, history, context, obsidian, greeting."""
from routes._common import (
    ValidationError,
    bp,
    json,
    jsonify,
    log,
    memory,
    request,
)


# ---------- OBSIDIAN BRIDGE (productivity) ----------
@bp.get("/obsidian")
def obsidian_status():
    from ai import obsidian
    available = obsidian.is_available()
    return jsonify({
        "available": available,
        "vault": str(obsidian.find_vault() or ""),
        "notes": obsidian.list_notes(limit=10) if available else [],
    })


@bp.post("/obsidian/save")
def obsidian_save():
    from ai import obsidian
    d = request.get_json(silent=True) or {}
    content = (d.get("content") or "").strip()
    if not content:
        raise ValidationError("Missing 'content'.")
    if not obsidian.is_available():
        raise ValidationError("Obsidian vault not configured "
                              "(set OBSIDIAN_VAULT in .env).")
    path = obsidian.save_note(content)
    return jsonify({"ok": True, "path": path})


# ---------- MEMORY ----------
@bp.get("/memory")
def memory_list():
    return jsonify({"facts": memory.all_facts(limit=200)})


@bp.post("/memory")
def memory_add():
    d = request.get_json(silent=True) or {}
    fact = (d.get("fact") or "").strip()
    cat = (d.get("category") or "manual").strip()
    if not fact:
        raise ValidationError("Empty fact.")
    mid = memory.remember(fact, category=cat, source="manual")
    return jsonify({"ok": True, "id": mid})


# ---------- HISTORY ----------
@bp.get("/history")
def history_list():
    return jsonify({"sessions": memory.all_sessions(limit=100)})


@bp.get("/history/<sid>")
def history_get(sid):
    if not sid:
        raise ValidationError("Missing session id.")
    from ai.conversation import clean_messages
    return jsonify({"session": sid,
                    "messages": clean_messages(memory.load_full_session(sid))})


# ---------- CONTEXT ----------
@bp.get("/context")
def context_get():
    from memory import context as ctx_tracker
    return jsonify({
        "recent": ctx_tracker.recent_events(minutes=120, limit=30),
        "errors": ctx_tracker.recent_errors(hours=24, limit=10),
        "last_session": ctx_tracker.last_session_summary(),
    })


@bp.get("/greeting")
def greeting_endpoint():
    from ai.proactive import startup_greeting
    title = "sir"
    try:
        from memory import get_pref
        title = get_pref("user_title", "sir") or "sir"
    except Exception:
        pass
    return jsonify({"greeting": startup_greeting(title)})


@bp.get("/briefing")
def briefing_endpoint():
    from system import scheduler
    return jsonify({"briefing": scheduler.compose_briefing()})


@bp.post("/opencode/start")
def opencode_start_route():
    from skills.opencode_bridge import start_server
    return jsonify({"ok": start_server()})


@bp.post("/opencode/stop")
def opencode_stop_route():
    from skills.opencode_bridge import stop_server
    stop_server()
    return jsonify({"ok": True})


@bp.get("/opencode/status")
def opencode_status_route():
    from skills.opencode_bridge import is_running
    return jsonify({"running": is_running()})


@bp.post("/opencode/web")
def opencode_web_route():
    """Open a visible terminal running `opencode web` (the web UI).

    Never starts a duplicate server: if the port already answers,
    just returns the URL so the frontend can open the tab.
    """
    from skills.opencode_bridge import launch_web_terminal
    r = launch_web_terminal()
    if not r.get("ok"):
        raise ValidationError(r.get("error") or "Launch failed.")
    return jsonify(r)


@bp.get("/opencode/ready")
def opencode_ready_route():
    """True once the OpenCode web server answers HTTP (ready for a tab)."""
    from skills.opencode_bridge import is_web_up, web_url
    return jsonify({"ready": is_web_up(), "url": web_url()})


@bp.get("/opencode/models")
def opencode_models_list():
    from skills.opencode_models import get_active_model, list_models
    return jsonify({
        "models": list_models(),
        "active": get_active_model(),
    })


@bp.post("/opencode/model")
def opencode_model_set():
    d = request.get_json(silent=True) or {}
    mid = (d.get("id") or "").strip()
    if not mid:
        raise ValidationError("Missing 'id'.")
    from skills.opencode_models import set_active_model
    if not set_active_model(mid):
        raise ValidationError("Could not save model.")
    return jsonify({"ok": True, "active": mid})


@bp.get("/opencode/model")
def opencode_model_get():
    from skills.opencode_models import get_active_model
    return jsonify({"active": get_active_model()})


@bp.post("/opencode/chat")
def opencode_chat():
    """Stream opencode CLI output for a given message."""
    import os
    import shutil
    import subprocess

    from flask import Response

    d = request.get_json(silent=True) or {}
    message = (d.get("message") or "").strip()
    model = (d.get("model") or "").strip()
    if not message:
        raise ValidationError("Empty message.")
    if len(message) > 4000:
        raise ValidationError("Message too long.")
    if not model:
        try:
            from skills.opencode_models import get_active_model
            model = get_active_model() or ""
        except Exception:
            model = ""

    exe = None
    for name in ("opencode.cmd", "opencode.exe", "opencode"):
        exe = shutil.which(name)
        if exe:
            break
    if not exe:
        raise ValidationError("opencode CLI not found on PATH.")

    def generate():
        cmd = [exe, "run", message]
        if model:
            cmd += ["--model", model]
        try:
            kw = {
                "stdout": subprocess.PIPE,
                "stderr": subprocess.STDOUT,
                "stdin": subprocess.DEVNULL,
                "text": True,
                "encoding": "utf-8",
                "errors": "replace",
                "bufsize": 1,
            }
            if os.name == "nt":
                kw["creationflags"] = subprocess.CREATE_NO_WINDOW
            proc = subprocess.Popen(cmd, **kw)
            try:
                for line in iter(proc.stdout.readline, ""):
                    yield f"data: {json.dumps({'delta': line})}\n\n"
            finally:
                try:
                    proc.stdout.close()
                except Exception:
                    pass
            proc.wait(timeout=300)
        except Exception as exc:
            log.exception("opencode chat failed")
            yield f"data: {json.dumps({'error': str(exc)[:200]})}\n\n"
        yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "Connection": "keep-alive",
    })


@bp.get("/update/check")
def update_check():
    """Fetch origin and report whether a newer JARVIS exists."""
    from system import updater
    return jsonify(updater.check())


@bp.post("/update/apply")
def update_apply():
    """Fast-forward the checkout to origin/main (never over local edits)."""
    from system import updater
    return jsonify(updater.update())


@bp.get("/health")
def health():
    """One snapshot of every subsystem (config, memory, guard, MCP, ...)."""
    from system import health as healthmon
    return jsonify(healthmon.snapshot())


@bp.post("/services/<name>")
def service_control(name):
    """Stop or restart one boot service (SYSTEM tab lifecycle buttons)."""
    from system import services
    d = request.get_json(silent=True) or {}
    action = (d.get("action") or "").strip().lower()
    if action not in ("stop", "restart"):
        raise ValidationError(
            "Bad service action.",
            detail="Field 'action' must be 'stop' or 'restart'.")
    if services.describe(name) is None:
        raise ValidationError("Unknown service.",
                              detail=f"Unknown service '{name}'.")
    try:
        if action == "stop":
            rec = services.stop_service(name)
        else:
            rec = services.restart(name)
    except ValueError as exc:  # no stop handler / boot-only service
        raise ValidationError("Service cannot be cycled.",
                              detail=str(exc))
    if not rec.get("ok", False):
        raise ValidationError(
            f"Service {action} failed.",
            detail=str(rec.get("detail") or "unknown error"))
    return jsonify({"ok": True, "name": name, "action": action,
                    "service": rec})


@bp.post("/webhook/in")
def webhook_in():
    """Inbound n8n/automation bridge (token or localhost gated)."""
    from skills import webhook_bridge
    body, code = webhook_bridge.ingest(
        request.get_json(silent=True) or {},
        request.headers.get("X-Jarvis-Token"),
        request.remote_addr)
    return jsonify(body), code


@bp.get("/webhook/recent")
def webhook_recent():
    """Last events delivered by automations this session."""
    from skills import webhook_bridge
    return jsonify({"events": webhook_bridge.recent()})


@bp.post("/interleave")
def interleave():
    """Append/insert into an allow-listed file with a .bak backup."""
    from skills.workspace_tools import append_to_file, insert_near
    d = request.get_json(silent=True) or {}
    path = (d.get("path") or "").strip()
    body = (d.get("body") or "").strip()
    if not path or not body:
        raise ValidationError("Need 'path' and 'body'.")
    anchor = (d.get("anchor") or "").strip()
    if anchor:
        where = "before" if str(d.get("position", "after")).lower() \
            == "before" else "after"
        out = insert_near(path, body, anchor, where)
    else:
        out = append_to_file(path, body)
    ok = not out.startswith(("Blocked:", "No such", "Nothing",
                             "Anchor not", "Need both", "No such file"))
    return jsonify({"ok": ok, "result": out})
