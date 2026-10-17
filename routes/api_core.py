"""routes.api_core — info, models, moods, tools, prefs, API key, logs, harness."""
from routes._common import (
    VERSION,
    AIError,
    ValidationError,
    _theme_dict,
    _to_int,
    all_skills,
    all_tools,
    bp,
    build_fallback_list,
    current_voice,
    get_active,
    get_cache,
    harness,
    jsonify,
    label_for,
    log,
    memory,
    moods,
    os,
    request,
    set_active,
    set_cache,
    speak_async,
    sys,
    theme_for,
    toggle_tool,
    try_settings,
)


@bp.get("/info")
def info():
    s = try_settings()
    key_ok = bool(s and s.has_key)
    active = get_active() or "auto"
    try:
        from memory import all_facts
        from skills import auto_generator as _ag
        facts = len(all_facts(limit=500))
        auto_approve = _ag.auto_approve_enabled()
    except Exception:
        facts, auto_approve = -1, None
    try:
        voice = current_voice()
    except Exception:
        voice = {"label": "Unavailable", "key": "none"}
    return jsonify({
        "version": VERSION,
        "model": active,
        "model_label": "Auto" if active == "auto" else label_for(active),
        "default_model": s.model if s else "deepseek-chat",
        "key": key_ok,
        "no_key_mode": not key_ok,
        "voice": voice,
        "mood": moods.current_name(),
        "moods": moods.all_moods(),
        "skills": [sk.name for sk in all_skills()],
        "facts": facts,
        "auto_approve": auto_approve,
        "dev": bool(s and getattr(s, "debug", False)),
        "theme": _theme_dict("auto" if active == "auto" else active),
    })


# ---------- MODELS ----------
@bp.get("/models")
def models_list():
    cached = get_cache()
    if cached:
        return jsonify({"models": cached, "active": get_active()})
    try:
        from ai.client import list_all_models
        items = list_all_models()
    except Exception as exc:
        log.warning("models_list failed, using fallback: %s", exc)
        items = build_fallback_list()
    set_cache(items)
    return jsonify({"models": items, "active": get_active()})


@bp.get("/diagnostics")
def diagnostics():
    import importlib
    info = {"python": f"{sys.version_info.major}.{sys.version_info.minor}",
            "modules": {}, "chromium": False, "config": False, "key": False}
    for mod in ["flask", "dotenv", "openai", "edge_tts", "pygame",
                "faster_whisper", "sounddevice", "playwright", "numpy"]:
        try:
            importlib.import_module(mod)
            info["modules"][mod] = True
        except ImportError:
            info["modules"][mod] = False
    try:
        from config import get_settings
        get_settings()
        info["config"] = True
    except Exception:
        pass
    try:
        from skills.browser_agent import _HAS
        info["chromium"] = bool(_HAS)
    except Exception:
        pass
    try:
        s = get_settings()
        info["key"] = bool(s.api_key and not s.api_key.startswith("sk-paste"))
    except Exception:
        pass
    return jsonify(info)


@bp.get("/stats")
def stats_endpoint():
    try:
        import psutil
        cpu = int(psutil.cpu_percent(interval=0.1))
        ram = int(psutil.virtual_memory().percent)
        bat = getattr(psutil, "sensors_battery", lambda: None)()
        battery = int(bat.percent) if bat else -1
        net = psutil.net_io_counters()
        net_mb = (net.bytes_sent + net.bytes_recv) // (1024 * 1024)
        return jsonify({"cpu": cpu, "ram": ram,
                        "battery": battery, "net": net_mb})
    except Exception as exc:
        return jsonify({"cpu": 0, "ram": 0, "battery": -1, "net": 0,
                        "error": str(exc)[:100]})


@bp.post("/model")
def model_set():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        raise ValidationError("Missing 'name'.")
    set_active(name)
    if name == "auto":
        speak_async("Auto routing enabled.")
        return jsonify({"ok": True, "model": "auto", "model_label": "Auto",
                        "theme": _theme_dict("auto")})
    t = theme_for(name)
    speak_async(f"Switched to {t.label}.")
    return jsonify({"ok": True, "model": name,
                    "model_label": label_for(name),
                    "theme": _theme_dict(name)})


# ---------- MOODS ----------
@bp.post("/mood")
def set_mood():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    m = moods.set_mood(name)
    if not m:
        raise ValidationError(f"Unknown mood: {name}")
    speak_async(f"Switching to {m.name} mood.")
    return jsonify({"ok": True, "mood": m.name, "description": m.description})


# ---------- TOOLS ----------
@bp.get("/tools")
def tools_list():
    return jsonify({"tools": all_tools()})


@bp.post("/tool")
def tool_toggle():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    enabled = bool(d.get("enabled", True))
    if not name:
        raise ValidationError("Missing 'name'.")
    if not toggle_tool(name, enabled):
        raise ValidationError(f"Unknown tool: {name}")
    return jsonify({"ok": True, "name": name, "enabled": enabled})


# ---------- PREFS ----------
@bp.get("/prefs")
def prefs_get():
    return jsonify({"prefs": memory.all_prefs()})


@bp.post("/prefs")
def prefs_set():
    d = request.get_json(silent=True) or {}
    key = (d.get("key") or "").strip()
    if not key:
        raise ValidationError("Missing 'key'.")
    if "value" not in d:
        raise ValidationError("Missing 'value'.")
    if not memory.set_pref(key, d["value"]):
        raise ValidationError(f"Unknown preference: {key}")
    return jsonify({"ok": True, "prefs": memory.all_prefs()})


# ---------- API KEY (in-app setup; keys live in .env, never prefs) ----------
@bp.get("/settings/key")
def settings_key_get():
    import config as _cfg
    st = _cfg.key_status()
    s = _cfg.try_settings()
    base = s.base_url if s else os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    return jsonify({"configured": st["ok"], "masked": _cfg.masked_key(),
                    "base_url": base})


@bp.post("/settings/key")
def settings_key_set():
    import config as _cfg
    d = request.get_json(silent=True) or {}
    key = _cfg.validate_key_format(d.get("key"))
    s = _cfg.try_settings()
    base = s.base_url if s else os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    try:
        from openai import OpenAI
        probe = OpenAI(api_key=key, base_url=base, timeout=20)
        found = probe.models.list()
        n_models = len(found.data or [])
    except ValidationError:
        raise
    except Exception as exc:
        raise AIError("Key verification failed.",
                      detail=f"{base}: {exc}"[:200])
    _cfg.write_env_key(key)
    os.environ["DEEPSEEK_API_KEY"] = key
    _cfg._settings = None
    try:
        from ai import client as _ac
        _ac._clients = {}
        _ac._model_ids_cache = {}
    except Exception:
        pass
    log.info("API key updated via Settings (verified, %d models).", n_models)
    return jsonify({"ok": True, "masked": _cfg.masked_key(),
                    "verified_models": n_models,
                    "restart_recommended": True})


@bp.get("/code-mode/audit")
def code_mode_audit():
    from pathlib import Path
    p = Path(__file__).resolve().parent.parent / "logs" / "code_mode_audit.log"
    if not p.exists():
        return jsonify({"entries": []})
    lines = p.read_text(encoding="utf-8").splitlines()
    return jsonify({"entries": lines[-100:]})


@bp.get("/personality")
def personality_get():
    from moods import personality
    return jsonify({
        "current": personality.current_dict(),
        "presets": personality.all_presets(),
    })

@bp.post("/personality/preset")
def personality_preset():
    from moods import personality
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip().lower()
    if not name:
        raise ValidationError("Missing 'name'.")
    p = personality.set_preset(name)
    if not p:
        raise ValidationError(f"Unknown preset: {name}")
    memory.set_pref("personality_preset", name)
    speak_async(f"Personality: {p.name}.")
    return jsonify({"ok": True, "current": personality.current_dict()})

@bp.post("/personality/custom")
def personality_custom():
    from moods import personality
    d = request.get_json(silent=True) or {}
    f = _to_int(d.get("formality", 50), 50, 0, 100)
    h = _to_int(d.get("humor", 50), 50, 0, 100)
    v = _to_int(d.get("verbosity", 50), 50, 0, 100)
    personality.set_values(f, h, v)
    memory.set_pref("personality_preset", "custom")
    memory.set_pref("personality_formality", f)
    memory.set_pref("personality_humor", h)
    memory.set_pref("personality_verbosity", v)
    return jsonify({"ok": True, "current": personality.current_dict()})


# ---------- HARNESS ----------
@bp.get("/harness/files")
def harness_files():
    return jsonify({"files": harness.list_files()})


@bp.get("/harness/file")
def harness_file():
    path = request.args.get("path", "")
    return jsonify({"path": path, "content": harness.read_file(path)})


@bp.post("/harness/propose")
def harness_propose():
    d = request.get_json(silent=True) or {}
    p = harness.self_edit.propose(d.get("file", ""), d.get("old", ""),
                                  d.get("new", ""), d.get("reason", ""))
    if "error" in p:
        raise ValidationError(p["error"])
    return jsonify(p)


@bp.post("/harness/apply")
def harness_apply():
    d = request.get_json(silent=True) or {}
    r = harness.self_edit.apply(d.get("id", ""))
    if "error" in r:
        raise ValidationError(r["error"])
    return jsonify(r)


# ---------- LOGS ----------
_LOG_ALLOW = {"jarvis.log", "dream_mode.log", "auto_skills.log",
              "clipboard_history.log"}


@bp.get("/logs/tail")
def logs_tail():
    from pathlib import Path
    name = (request.args.get("file", "jarvis.log") or "").strip()
    if "/" in name or "\\" in name or name not in _LOG_ALLOW:
        raise ValidationError("Log not allowed.")
    try:
        lines = int(request.args.get("lines", 80))
    except Exception:
        lines = 80
    lines = max(1, min(500, lines))
    p = Path(__file__).resolve().parent.parent / "logs" / name
    if not p.exists():
        return jsonify({"file": name, "lines": []})
    try:
        data = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception as exc:
        raise ValidationError(f"Cannot read log: {exc}")
    return jsonify({"file": name, "lines": data[-lines:]})


# ---------- AUDIT ----------
@bp.get("/audit")
def audit_tail():
    """Newest-first agent audit lines: tool calls, consent verdicts,
    mission steps. Tail only, never the whole file. Never raises —
    worst case an empty list."""
    from system import audit as _trail
    try:
        limit = int(request.args.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    entries = _trail.read_tail(limit)
    return jsonify({"entries": entries, "count": len(entries)})


