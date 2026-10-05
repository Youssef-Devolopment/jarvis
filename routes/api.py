from __future__ import annotations
import json
import os
import sys
import threading
from flask import Blueprint, Response, jsonify, request
from ai import get_client, get_store, extract_memory_async
from ai.tools import TOOL_SCHEMAS
from config import get_settings, try_settings, VERSION
from errors import AIError, ConfigError, ValidationError, VoiceError
from logger import get_logger
from skills import dispatch as dispatch_skill, all_skills, toggle_skill
from tools import all_tools, toggle_tool, filtered_schemas
from mcp import all_servers as mcp_list, add_server as mcp_add, \
                remove_server as mcp_remove, toggle_server as mcp_toggle
try:
    from voice import (speak_async, listen_until_silence,
                       set_voice as set_voice_impl, current_voice, all_voices)
except Exception as _voice_import_exc:
    # Skills-only (no-key) boot: voice/output.py reads settings at import.
    # Stub the entry points so text endpoints stay up; voice endpoints
    # fail loudly with a clear error instead of killing the import chain.
    # (Copied to a plain module global: `except ... as` names are
    # deleted when the block exits.)
    _voice_import_detail = str(_voice_import_exc)[:120]
    log = get_logger(__name__)
    log.warning("Voice subsystem unavailable (%s). Text chat and skills "
                "are unaffected.", _voice_import_detail)

    def _voice_down(*_a, **_k):
        raise VoiceError("Voice subsystem unavailable.",
                         detail=_voice_import_detail)
    speak_async = listen_until_silence = set_voice_impl = \
        current_voice = all_voices = _voice_down


def _speak_quiet(text: str) -> None:
    """Best-effort TTS for chat replies: a dead speaker must never
    turn a good text answer into a failed request."""
    try:
        speak_async(text)
    except Exception as exc:
        get_logger(__name__).warning("speak failed (reply kept): %s", exc)


def _to_int(value, default: int, lo: int | None = None,
            hi: int | None = None) -> int:
    """Parse user-supplied ints defensively: garbage becomes the
    default, extremes get clamped. Never raises."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v
from moods.models import (get_active, set_active, set_cache, get_cache,
                           theme_for, label_for, build_fallback_list)
from moods.router import needs_reasoning
from moods import classifier, council, moderator
from moods.levels import Level, LEVEL_SPECS
from memory import outcomes
from ai import reality_check
from ai import agents
from ai import dream_mode
from ai import (clipboard_watcher, quick_capture, screen_text,
                focus_lock, snippets, window_layouts, url_cleaner,
                auto_format, time_tracker)
import moods, memory, harness

log = get_logger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")


def _theme_dict(model_name: str) -> dict:
    t = theme_for(model_name)
    return {"hue": t.hue, "accent": t.accent, "label": t.label}


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


# ---------- VOICES ----------
@bp.get("/voices")
def voices_list():
    try:
        return jsonify({"voices": all_voices(),
                        "active": current_voice()["key"]})
    except VoiceError:
        return jsonify({"voices": [], "active": "none",
                        "unavailable": True})


@bp.post("/voice")
def voice_set():
    d = request.get_json(silent=True) or {}
    key = (d.get("key") or "").strip()
    if not key:
        raise ValidationError("Missing 'key'.")
    v = set_voice_impl(key)
    if not v:
        raise ValidationError(f"Unknown voice: {key}")
    speak_async(f"Hello, I am {v['label']}. This is my voice.")
    return jsonify({"ok": True, "voice": current_voice()})


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


@bp.get("/models/featured")
def models_featured():
    from moods.models import featured_models, get_active
    return jsonify({"models": featured_models(), "active": get_active()})


@bp.post("/models/test")
def models_test():
    from moods.models import set_working
    import time
    d = request.get_json(silent=True) or {}
    ids = d.get("ids") or []
    if not ids:
        from moods.models import FEATURED
        ids = [m["id"] for m in FEATURED if m["id"] != "auto"]
    client = get_client()
    results = []
    for mid in ids:
        t0 = time.time()
        try:
            r = client._client.chat.completions.create(
                model=mid,
                messages=[{"role": "user", "content": "Reply with the single word: ok"}],
                max_tokens=10,
                temperature=0,
            )
            reply = (r.choices[0].message.content or "").strip().lower()
            ok = "ok" in reply
            ms = int((time.time() - t0) * 1000)
            set_working(mid, ok, f"{ms}ms")
            results.append({"id": mid, "ok": ok, "ms": ms, "reply": reply[:40]})
        except Exception as exc:
            set_working(mid, False, str(exc)[:120])
            results.append({"id": mid, "ok": False, "error": str(exc)[:120]})
    return jsonify({"results": results})


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


# ---------- SKILLS ----------
@bp.get("/skills")
def skills_list():
    return jsonify({
        "skills": [
            {"name": sk.name, "description": sk.description, "enabled": sk.enabled}
            for sk in all_skills()
        ]
    })


@bp.post("/skill")
def skill_toggle():
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    enabled = bool(d.get("enabled", True))
    if not name:
        raise ValidationError("Missing 'name'.")
    if not toggle_skill(name, enabled):
        raise ValidationError(f"Unknown skill: {name}")
    return jsonify({"ok": True, "name": name, "enabled": enabled})


# ---------- AUTO SKILLS ----------
@bp.get("/auto_skills/pending")
def auto_skills_pending():
    from skills import auto_generator as _ag
    return jsonify({"pending": _ag.list_pending(),
                    "enabled": _ag.auto_gen_enabled(),
                    "auto_approve": _ag.auto_approve_enabled()})


@bp.post("/auto_skills/approve")
def auto_skills_approve():
    from skills import auto_generator as _ag
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        raise ValidationError("Missing 'name'.")
    r = _ag.approve_skill(name)
    if not r.get("ok"):
        raise ValidationError(r.get("error") or "Approve failed.")
    return jsonify({"ok": True, "name": r["name"]})


@bp.post("/auto_skills/reject")
def auto_skills_reject():
    from skills import auto_generator as _ag
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    if not name:
        raise ValidationError("Missing 'name'.")
    r = _ag.reject_skill(name)
    if not r.get("ok"):
        raise ValidationError(r.get("error") or "Reject failed.")
    return jsonify({"ok": True, "name": r["name"]})


@bp.post("/auto_skills/auto_approve")
def auto_skills_auto_approve():
    """Toggle the durable bypass gate for test-passed candidates."""
    from skills import auto_generator as _ag
    d = request.get_json(silent=True) or {}
    if "enabled" not in d:
        raise ValidationError("Missing 'enabled'.")
    if not _ag.set_auto_approve_enabled(bool(d.get("enabled"))):
        raise ValidationError("Could not save auto-approve preference.")
    return jsonify({"ok": True, "auto_approve": _ag.auto_approve_enabled()})


@bp.post("/auto_skills/enabled")
def auto_skills_enabled():
    from skills import auto_generator as _ag
    d = request.get_json(silent=True) or {}
    ok = _ag.set_auto_gen_enabled(bool(d.get("enabled", True)))
    if not ok:
        raise ValidationError("Could not save preference.")
    return jsonify({"ok": True, "enabled": _ag.auto_gen_enabled()})


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
    from skills import all_skills
    from skills import auto_generator as _ag
    from plugins import status as plugins_status
    from mcp.presets import list_presets
    from mcp.manager import all_servers
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


# ---------- COUNCIL ----------
@bp.post("/council/run")
def council_run():
    """Run a council at an explicit level."""
    from moods.council import run_council
    from moods.moderator import synthesize

    d = request.get_json(silent=True) or {}
    question = (d.get("question") or "").strip()
    level_name = (d.get("level") or "council").strip().lower()

    if not question:
        raise ValidationError("Missing 'question'.")

    # Map name → Level
    level = None
    for lv, spec in LEVEL_SPECS.items():
        if spec.name == level_name:
            level = lv
            break
    if level is None:
        raise ValidationError(f"Unknown level: {level_name}")

    # Confirmation gate for expensive levels (L7+).
    if int(level) >= int(Level.COUNCIL_MAX) \
            and not d.get("confirm", False):
        spec = LEVEL_SPECS[level]
        return jsonify({
            "ok": False,
            "needs_confirmation": True,
            "level": spec.name,
            "cost_estimate": spec.estimated_cost_usd,
            "timeout": spec.timeout_sec,
        })

    result = run_council(question, level)
    if not result.get("ok"):
        return jsonify({"ok": False, "error": "no model succeeded",
                        "results": result.get("results", [])})

    final = synthesize(question, result)
    return jsonify({
        "ok": final.get("ok"),
        "answer": final.get("answer"),
        "confidence": final.get("confidence"),
        "level": result.get("level"),
        "elapsed": result.get("elapsed"),
        "ok_count": result.get("ok_count"),
        "total_count": result.get("total_count"),
    })


@bp.get("/council/levels")
def council_levels():
    return jsonify({
        "levels": [
            {
                "name": spec.name,
                "level": int(lv),
                "models": len(spec.models),
                "timeout": spec.timeout_sec,
                "cost_estimate": spec.estimated_cost_usd,
            }
            for lv, spec in sorted(LEVEL_SPECS.items())
        ]
    })


# ---------- OUTCOMES + REALITY CHECK ----------
@bp.get("/outcomes/stats")
def outcomes_stats():
    return jsonify(outcomes.stats())


@bp.get("/outcomes/rejected")
def outcomes_rejected():
    return jsonify({"rejected": outcomes.recent_rejected(limit=20)})


@bp.post("/reality-check")
def reality_check_endpoint():
    """Manually verify an answer."""
    d = request.get_json(silent=True) or {}
    question = (d.get("question") or "").strip()
    answer = (d.get("answer") or "").strip()
    if not (question and answer):
        raise ValidationError("Missing 'question' or 'answer'.")
    result = reality_check.verify(question, answer)
    return jsonify(result)


# ---------- AGENTS ----------
@bp.post("/agents/run")
def agents_run():
    """Run an autonomous multi-agent session."""
    d = request.get_json(silent=True) or {}
    question = (d.get("question") or "").strip()
    if not question:
        raise ValidationError("Missing 'question'.")

    result = agents.run(question)
    return jsonify({
        "ok": result.get("ok"),
        "mode": result.get("mode"),
        "answer": result.get("answer"),
        "tasks": result.get("tasks"),
        "ok_tasks": result.get("ok_tasks"),
        "elapsed": result.get("elapsed"),
        "sub_results": [
            {"task": r.get("task"), "ok": r.get("ok"),
             "elapsed": r.get("elapsed")}
            for r in (result.get("sub_results") or [])
        ],
    })


# ---------- DREAM MODE ----------
@bp.post("/dream/run")
def dream_run():
    """Trigger Dream Mode manually (or dry-run)."""
    d = request.get_json(silent=True) or {}
    dry_run = bool(d.get("dry_run", False))
    result = dream_mode.run_dream(dry_run=dry_run)
    return jsonify(result)


@bp.get("/dream/last")
def dream_last():
    return jsonify(dream_mode.get_last_report())


@bp.get("/dream/status")
def dream_status():
    from memory import get_pref
    return jsonify({
        "enabled": bool(get_pref("dream_enabled", False)),
        "start_hour": int(get_pref("dream_start_hour", 3)),
        "end_hour": int(get_pref("dream_end_hour", 5)),
    })


# ---------- QUICK CAPTURE / CLIPBOARD / DESK ----------
@bp.get("/clipboard/recent")
def clip_recent():
    return jsonify({"items": clipboard_watcher.recent(limit=15)})


@bp.get("/clipboard/suggestions")
def clip_sugg():
    consume = request.args.get("consume", "0") == "1"
    return jsonify({"suggestions": clipboard_watcher.pending_suggestions(consume)})


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
@bp.get("/screen/context")
def screen_context_status():
    from ai import screen_context
    return jsonify(screen_context.status())


@bp.post("/screen/context/start")
def screen_context_start():
    from ai import screen_context
    return jsonify({"started": screen_context.start()})


@bp.post("/screen/context/stop")
def screen_context_stop():
    from ai import screen_context
    screen_context.stop()
    return jsonify({"stopped": True})


@bp.post("/screen/ask")
def screen_ask():
    from ai import screen_context
    d = request.get_json(silent=True) or {}
    q = (d.get("question") or "").strip()
    text = screen_context.ask(q)
    return jsonify({"ok": not text.startswith("[error]"), "text": text})


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


@bp.get("/snippets/<int:sid>")
def snippet_get_ep(sid):
    s = snippets.get(sid)
    if not s: raise ValidationError("Snippet not found.")
    return jsonify(s)


@bp.delete("/snippets/<int:sid>")
def snippet_delete_ep(sid):
    return jsonify({"ok": snippets.delete(sid)})


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
@bp.get("/overlay/state")
def overlay_state():
    from system import overlay
    st = overlay._state
    th = st.get("thread")
    return jsonify({"ready": bool(overlay._ready.is_set()),
                    "visible": bool(st.get("visible")),
                    "thread_alive": bool(th and th.is_alive()),
                    "root": bool(st.get("root"))})


@bp.post("/overlay/toggle")
def overlay_toggle():
    from system import overlay
    threading.Thread(target=overlay.toggle, daemon=True).start()
    return jsonify({"ok": True})


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


@bp.post("/apps/refresh")
def apps_refresh():
    from ai import app_index
    apps = app_index.refresh()
    return jsonify({"ok": True, "count": len(apps)})


# ---------- APP LEARNER (autonomous skill generation) ----------
@bp.get("/apps/learned")
def apps_learned():
    from system import app_learner
    return jsonify({"count": len(app_learner.learned_list()),
                    "apps": app_learner.learned_list()})


@bp.post("/apps/learn")
def apps_learn():
    """Learn an app NOW (scan + write skill) without launching it."""
    from system import app_learner
    d = request.get_json(silent=True) or {}
    name = (d.get("name") or "").strip()
    path = (d.get("path") or "").strip()
    query = (d.get("query") or "").strip()
    try:
        if name and path:
            skill, created = app_learner.ensure_skill(name, path)
        elif query:
            hit = app_learner.find(query)
            if not hit:
                apps = app_learner.scan(force=True)
                from system.app_learner import _norm
                hit = apps.get(_norm(query))
            if not hit:
                return jsonify({"ok": False,
                                "error": f"no executable found for '{query}'"}), 404
            skill, created = app_learner.ensure_skill(hit["name"], hit["path"])
            name, path = hit["name"], hit["path"]
        else:
            raise ValidationError("Provide 'query' or 'name' + 'path'.")
        from skills.registry import get_skill
        live = bool(get_skill(skill))
        return jsonify({"ok": True, "skill": skill, "created": created,
                        "status": "live" if live else "pending",
                        "name": name, "path": path})
    except ValueError as exc:
        raise ValidationError(str(exc))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:160]}), 500


@bp.post("/apps/forget")
def apps_forget():
    from system import app_learner
    d = request.get_json(silent=True) or {}
    q = (d.get("query") or "").strip()
    if not q:
        raise ValidationError("Missing 'query'.")
    ok = app_learner.forget(q)
    if not ok:
        raise ValidationError(f"Nothing learned called '{q}'.")
    return jsonify({"ok": True, "forgotten": q})


@bp.post("/apps/close")
def apps_close():
    """Close a running app by name. Graceful first, verified after.

    Body: {"query": "notepad", "confirm": true}. Non-instant targets
    need confirm:true, unless auto mode is on (auto_approve_skills
    pref) which counts as a standing yes. System/self refusals apply.
    """
    from system import app_close
    d = request.get_json(silent=True) or {}
    q = (d.get("query") or "").strip()
    if not q:
        raise ValidationError("Missing 'query'.")
    confirmed = bool(d.get("confirm"))
    res = app_close.close_by_name(
        q, ask_fn=(lambda _d: True) if confirmed else None)
    code = 200 if (res.get("ok") or res.get("declined")) else 404
    return jsonify({"ok": bool(res.get("ok")), **res}), code


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


# ---------- DEEP RESEARCH (async jobs) ----------
@bp.post("/research")
def research_start():
    """Trigger a research job. Body: {"topic": "..."}. Poll status."""
    from system import research_agent as ra
    d = request.get_json(silent=True) or {}
    topic = (d.get("topic") or "").strip()
    if not topic:
        raise ValidationError("Missing 'topic'.")
    if len(topic) > 300:
        raise ValidationError("Topic too long.")
    return jsonify({"ok": True, **ra.start_research(topic)})


@bp.get("/research/<job_id>")
def research_poll(job_id):
    from system import research_agent as ra
    st = ra.job_status((job_id or "").strip())
    if st is None:
        return jsonify({"ok": False, "error": "Unknown job."}), 404
    return jsonify({"ok": True, **st})


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


@bp.post("/sites/refresh")
def sites_refresh():
    from ai import site_index
    data = site_index.refresh()
    return jsonify({"ok": True,
                    "bookmarks": len(data.get("bookmarks", [])),
                    "history": len(data.get("history", []))})


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


# ---------- MCP ----------
@bp.get("/mcp")
def mcp_all():
    return jsonify({"servers": mcp_list()})


@bp.get("/mcp/setup")
def mcp_setup():
    from mcp import presets
    return jsonify({"toolchain": presets.toolchain(),
                    "presets": presets.list_presets(),
                    "servers": mcp_list()})


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


@bp.post("/mcp/import")
def mcp_import():
    from mcp import presets
    d = request.get_json(silent=True) or {}
    cfg = d.get("config", d)
    if isinstance(cfg, str):
        import json as _json
        try:
            cfg = _json.loads(cfg)
        except Exception:
            raise ValidationError("config is not valid JSON.")
    r = presets.import_claude_config(cfg)
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


@bp.post("/mcp/remove")
def mcp_remove_route():
    d = request.get_json(silent=True) or {}
    sid = (d.get("id") or "").strip()
    if not sid:
        raise ValidationError("Missing 'id'.")
    if not mcp_remove(sid):
        raise ValidationError("Server not found.")
    return jsonify({"ok": True})


@bp.post("/mcp/toggle")
def mcp_toggle_route():
    d = request.get_json(silent=True) or {}
    sid = (d.get("id") or "").strip()
    enabled = bool(d.get("enabled", True))
    if not sid:
        raise ValidationError("Missing 'id'.")
    if not mcp_toggle(sid, enabled):
        raise ValidationError("Server not found.")
    return jsonify({"ok": True, "id": sid, "enabled": enabled})


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


@bp.get("/mcp/tools")
def mcp_tools_route():
    from mcp import runtime
    return jsonify({"tools": runtime.all_tools()})


@bp.get("/mcp/serve")
def mcp_serve_route():
    """Host config for JARVIS's own native MCP stdio server."""
    from mcp.presets import serve_config
    return jsonify(serve_config())


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


@bp.post("/obsidian/search")
def obsidian_search():
    from ai import obsidian
    d = request.get_json(silent=True) or {}
    q = (d.get("query") or "").strip()
    if not q:
        raise ValidationError("Missing 'query'.")
    if not obsidian.is_available():
        raise ValidationError("Obsidian vault not configured.")
    return jsonify({"notes": obsidian.search_notes(q, limit=15)})


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


@bp.post("/memory/forget")
def memory_forget():
    d = request.get_json(silent=True) or {}
    pat = (d.get("pattern") or "").strip()
    if not pat:
        raise ValidationError("Empty pattern.")
    n = memory.forget(pat)
    return jsonify({"ok": True, "deleted": n})


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


@bp.post("/prefs/reset")
def prefs_reset():
    memory.reset_prefs()
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


@bp.get("/autostart/status")
def autostart_status():
    try:
        from system.autostart import status
        return jsonify(status())
    except Exception as exc:
        return jsonify({"enabled": False, "error": str(exc)[:120]})


@bp.post("/autostart/enable")
def autostart_enable():
    try:
        from system.autostart import enable, status
        ok = enable()
        return jsonify({"ok": ok, **status()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:120]}), 500


@bp.post("/autostart/disable")
def autostart_disable():
    try:
        from system.autostart import disable
        ok = disable()
        return jsonify({"ok": ok, "enabled": not ok})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)[:120]}), 500


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


@bp.post("/harness/reject")
def harness_reject():
    d = request.get_json(silent=True) or {}
    return jsonify(harness.self_edit.reject(d.get("id", "")))


@bp.get("/harness/pending")
def harness_pending():
    return jsonify({"pending": harness.self_edit.pending()})


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


# ---------- VOICE ROUTES ----------
@bp.post("/speak")
def speak_route():
    d = request.get_json(silent=True) or {}
    text = (d.get("text") or "").strip()
    if not text:
        raise ValidationError("Empty text.")
    speak_async(text)
    return jsonify({"ok": True})


@bp.post("/listen")
def listen_route():
    try:
        text = listen_until_silence(verbose=False)
    except Exception as exc:
        log.exception("Listen failed")
        return jsonify({"error": str(exc), "hint": "Check logs/jarvis.log"}), 500
    if text is None:
        return jsonify({"text": "", "empty": True,
                        "hint": "Whisper may not be installed. Run: pip install faster-whisper"})
    return jsonify({"text": text, "empty": not bool(text)})


@bp.post("/clear")
def clear():
    d = request.get_json(silent=True) or {}
    sid = d.get("session")
    if not sid:
        raise ValidationError("Missing session.")
    return jsonify({"ok": True, "cleared": get_store().clear(sid)})


# ---------- TRANSCRIBE ----------
@bp.post("/transcribe")
def transcribe_route():
    if "audio" not in request.files:
        raise ValidationError("Missing 'audio' file.")
    f = request.files["audio"]
    data = f.read()
    if not data:
        raise ValidationError("Empty audio.")
    from voice import transcribe_audio_bytes
    suffix = "." + (f.filename or "x.webm").rsplit(".", 1)[-1]
    text = transcribe_audio_bytes(data, suffix=suffix)
    return jsonify({"text": text or "", "empty": not bool(text)})


# ---------- STOP SPEAK ----------
@bp.post("/stop-speak")
def stop_speak_route():
    try:
        from voice import stop_speaking
        stop_speaking()
    except Exception:
        pass
    return jsonify({"ok": True})


# ---------- HISTORY ----------
@bp.get("/history")
def history_list():
    return jsonify({"sessions": memory.all_sessions(limit=100)})


@bp.get("/history/<sid>")
def history_get(sid):
    if not sid:
        raise ValidationError("Missing session id.")
    return jsonify({"session": sid, "messages": memory.load_full_session(sid)})


@bp.post("/history/delete")
def history_delete():
    d = request.get_json(silent=True) or {}
    sid = (d.get("session") or "").strip()
    if not sid:
        raise ValidationError("Missing 'session'.")
    return jsonify(memory.delete_session(sid))


# ---------- COMMAND ----------
@bp.post("/command")
def command():
    d = request.get_json(silent=True) or {}
    text = (d.get("text") or "").strip()
    sid = (d.get("session") or "default").strip()
    if not text:
        raise ValidationError("Empty command.")
    if len(text) > 4000:
        raise ValidationError("Command too long.")

    # Check if this is a rejection of the previous answer
    if outcomes.detect_rejection(text):
        marked = outcomes.update_last(accepted=False, feedback=text)
        if marked:
            _speak_quiet("Understood. I'll avoid that approach, sir.")

    # Check if this is a confirmation
    elif outcomes.detect_confirmation(text):
        marked = outcomes.update_last(accepted=True, feedback=text)

    # Skip skills for purely conversational input
    from ai.self_awareness import is_conversational
    skill_reply = None
    if not is_conversational(text):
        skill_reply = dispatch_skill(text)
    if skill_reply:
        def s():
            yield f"data: {json.dumps({'delta': skill_reply, 'source': 'skill'})}\n\n"
            yield "data: [DONE]\n\n"
        _speak_quiet(skill_reply)
        return Response(s(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
            "Connection": "keep-alive"})

    # Auto-generate hook: approve/reject commands first, then draft on miss.
    if not is_conversational(text):
        try:
            from skills import auto_generator as _ag
            _handled = _ag.handle_approval_text(text)
            if _handled:
                def _sa():
                    yield f"data: {json.dumps({'delta': _handled, 'source': 'auto_skill'})}\n\n"
                    yield "data: [DONE]\n\n"
                try:
                    store0 = get_store()
                    store0.messages_for(sid, text)
                    store0.record_reply(sid, _handled)
                except Exception:
                    pass
                _speak_quiet(_handled)
                return Response(_sa(), mimetype="text/event-stream", headers={
                    "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                    "Connection": "keep-alive"})
            _proposal = _ag.propose_if_enabled(text)
        except Exception:
            _proposal = None
        if _proposal:
            _prompt = _ag.approval_prompt(_proposal)
            try:
                store1 = get_store()
                store1.messages_for(sid, text)
                store1.record_reply(sid, _prompt)
            except Exception:
                pass
            _speak_quiet(_prompt)

            def _sp():
                yield f"data: {json.dumps({'delta': _prompt, 'source': 'auto_skill'})}\n\n"
                yield "data: [DONE]\n\n"
            return Response(_sp(), mimetype="text/event-stream", headers={
                "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                "Connection": "keep-alive"})

    route = "reasoning" if needs_reasoning(text) else "fast"

    try:
        store = get_store()
        client = get_client()
    except ConfigError:
        msg = ("Skills-only mode: no API key set. Local skills (time, "
               "math, notes, timers, opening apps...) all work — add "
               "DEEPSEEK_API_KEY in .env (or Settings) and restart for "
               "full AI chat.")

        def _nok():
            yield f"data: {json.dumps({'route': route, 'error': msg, 'no_key': True})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(_nok(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
            "Connection": "keep-alive"})

    messages = store.messages_for(sid, text)
    from ai.tools import mcp_schemas
    schemas = filtered_schemas(TOOL_SCHEMAS) + mcp_schemas()

    def generate():
        collected = []
        yield f"data: {json.dumps({'route': route})}\n\n"
        try:
            for kind, payload in client.stream(messages, tools=schemas):
                if kind == "content":
                    collected.append(payload)
                    yield f"data: {json.dumps({'delta': payload, 'source': 'llm'})}\n\n"
                elif kind == "reasoning":
                    yield f"data: {json.dumps({'reasoning': payload})}\n\n"
                elif kind == "tool_call":
                    yield f"data: {json.dumps({'tool_call': payload})}\n\n"
                elif kind == "tool_result":
                    yield f"data: {json.dumps({'tool_result': payload})}\n\n"
        except AIError as exc:
            yield f"data: {json.dumps({'error': exc.public_message, 'detail': exc.detail})}\n\n"
        finally:
            full = "".join(collected).strip()
            if full:
                store.record_reply(sid, full)
                _speak_quiet(full)
                extract_memory_async(text, full)
                try:
                    outcomes.record(text, full)
                except Exception:
                    pass
            yield "data: [DONE]\n\n"

    return Response(generate(), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        "Connection": "keep-alive"})


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
    from skills.opencode_models import list_models, get_active_model
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
