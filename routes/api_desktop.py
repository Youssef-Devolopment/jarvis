"""routes.api_desktop — capture/clipboard, screen, terminal, ports, apps, sites."""
from routes._common import (
    ValidationError,
    _to_int,
    auto_format,
    bp,
    clipboard_watcher,
    focus_lock,
    jsonify,
    quick_capture,
    request,
    screen_text,
    snippets,
    time_tracker,
    url_cleaner,
    window_layouts,
)


# ---------- QUICK CAPTURE / CLIPBOARD / DESK ----------
@bp.get("/clipboard/recent")
def clip_recent():
    return jsonify({"items": clipboard_watcher.recent(limit=15)})


@bp.post("/capture")
def capture_ep():
    d = request.get_json(silent=True) or {}
    text = (d.get("text") or "").strip()
    if not text: raise ValidationError("Missing 'text'.")
    return jsonify(quick_capture.execute(text))


@bp.post("/ocr/screen")
def ocr_ep():
    text = screen_text.extract_text()
    return jsonify({"ok": not text.startswith("[error]"), "text": text})


# ---------- SCREEN CONTEXT (omniscience loop) ----------
@bp.get("/contacts")
def contacts_ep():
    from memory import list_contacts
    return jsonify({"contacts": list_contacts(limit=100)})


@bp.post("/contacts")
def contacts_save_ep():
    from memory import save_contact
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name: raise ValidationError("Missing 'name'.")
    cid = save_contact(name, phone=(d.get("phone") or "").strip(),
                       email=(d.get("email") or "").strip())
    return jsonify({"ok": bool(cid), "id": cid})


@bp.get("/reminders")
def reminders_ep():
    from memory import list_reminders
    return jsonify({"reminders": list_reminders(only_pending=True)})


@bp.post("/focus/start")
def focus_start_ep():
    d = request.get_json(silent=True) or {}
    mins = _to_int(d.get("minutes", 60), 60, 1, 480)
    ok = focus_lock.start(mins)
    return jsonify({"ok": ok, "minutes": mins})


@bp.post("/focus/stop")
def focus_stop_ep():
    focus_lock.stop()
    return jsonify({"ok": True})


@bp.get("/focus/status")
def focus_status_ep():
    return jsonify(focus_lock.status())


@bp.get("/snippets")
def snippets_ep():
    q = request.args.get("q", "")
    return jsonify({"snippets": snippets.list_all(query=q)})


@bp.post("/snippets")
def snippets_save_ep():
    d = request.get_json(silent=True) or {}
    title = (d.get("title") or "").strip()
    code = d.get("code") or ""
    if not title or not code: raise ValidationError("Missing title or code.")
    return jsonify(snippets.save(title, code,
                                 language=(d.get("language") or ""),
                                 tags=(d.get("tags") or "")))


@bp.get("/layouts")
def layouts_ep():
    return jsonify({"layouts": window_layouts.list_layouts()})


@bp.post("/layouts/save")
def layout_save_ep():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name: raise ValidationError("Missing name.")
    return jsonify(window_layouts.save(name))


@bp.post("/layouts/restore")
def layout_restore_ep():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name: raise ValidationError("Missing name.")
    return jsonify(window_layouts.restore(name))


@bp.post("/url/clean")
def url_clean_ep():
    return jsonify(url_cleaner.clean_clipboard())


@bp.post("/format")
def format_ep():
    d = request.get_json(silent=True) or {}
    text = d.get("text") or ""
    mode = d.get("mode", "auto")
    if not text: raise ValidationError("Missing 'text'.")
    return jsonify(auto_format.format_text(text, mode=mode))


@bp.get("/time/summary")
def time_summary_ep():
    hours = _to_int(request.args.get("hours", 24), 24, 1, 168)
    return jsonify({"entries": time_tracker.summary(hours=hours)})


# ---------- TERMINAL ----------
@bp.post("/terminal/run")
def terminal_run():
    from ai import tools_terminal
    d = request.get_json(silent=True) or {}
    cmd = (d.get("command") or "").strip()
    if not cmd:
        raise ValidationError("Missing 'command'.")
    try:
        timeout = int(d.get("timeout", 30))
    except Exception:
        timeout = 30
    timeout = max(1, min(120, timeout))
    return jsonify({"output": tools_terminal.term_run(cmd, timeout)})


# ---------- PORTS ----------
@bp.get("/ports")
def ports_list():
    from ai import ports
    items = ports.list_listeners()
    return jsonify({"count": len(items), "ports": items[:60]})


@bp.post("/ports/kill")
def ports_kill():
    from ai import ports
    d = request.get_json(silent=True) or {}
    r = ports.kill_listener(d.get("pid", 0), d.get("port", 0) or 0)
    if not r.get("ok"):
        raise ValidationError(r.get("error") or "Kill failed.")
    return jsonify(r)


# ---------- OVERLAY (Alt+Space HUD) ----------
# ---------- APP INDEX ----------
@bp.get("/apps")
def apps_list():
    from ai import app_index
    q = request.args.get("q", "").strip()
    apps = app_index.load_index()
    if q:
        hit = app_index.find(q)
        apps = [hit] if hit else []
    return jsonify({"count": len(apps), "apps": apps[:100]})


# ---------- SITE INDEX ----------
@bp.get("/sites")
def sites_list():
    from ai import site_index
    data = site_index.load_index()
    return jsonify({"bookmarks": len(data.get("bookmarks", [])),
                    "history": len(data.get("history", [])),
                    "top": sorted(data.get("history", []),
                                  key=lambda h: h.get("visits", 0),
                                  reverse=True)[:20]})


