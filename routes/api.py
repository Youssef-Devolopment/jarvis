from __future__ import annotations
import json
import sys
from flask import Blueprint, Response, jsonify, request
from ai import get_client, get_store, extract_memory_async
from ai.tools import TOOL_SCHEMAS
from config import get_settings
from errors import AIError, ValidationError
from logger import get_logger
from skills import dispatch as dispatch_skill, all_skills, toggle_skill
from tools import all_tools, toggle_tool, filtered_schemas
from mcp import all_servers as mcp_list, add_server as mcp_add, \
                remove_server as mcp_remove, toggle_server as mcp_toggle
from voice import (speak_async, listen_until_silence,
                   set_voice as set_voice_impl, current_voice, all_voices)
from moods.models import (get_active, set_active, set_cache, get_cache,
                           theme_for, label_for, build_fallback_list)
from moods.router import needs_reasoning
from moods import classifier, council, moderator
from moods.levels import Level, LEVEL_SPECS
import moods, memory, harness

log = get_logger(__name__)
bp = Blueprint("api", __name__, url_prefix="/api")


def _theme_dict(model_name: str) -> dict:
    t = theme_for(model_name)
    return {"hue": t.hue, "accent": t.accent, "label": t.label}


@bp.get("/info")
def info():
    s = get_settings()
    active = get_active() or "auto"
    return jsonify({
        "model": active,
        "model_label": "Auto" if active == "auto" else label_for(active),
        "default_model": s.model,
        "voice": current_voice(),
        "mood": moods.current_name(),
        "moods": moods.all_moods(),
        "skills": [sk.name for sk in all_skills()],
        "theme": _theme_dict("auto" if active == "auto" else active),
    })


# ---------- VOICES ----------
@bp.get("/voices")
def voices_list():
    return jsonify({"voices": all_voices(), "active": current_voice()["key"]})


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
                    "enabled": _ag.auto_gen_enabled()})


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


@bp.post("/auto_skills/enabled")
def auto_skills_enabled():
    from skills import auto_generator as _ag
    d = request.get_json(silent=True) or {}
    ok = _ag.set_auto_gen_enabled(bool(d.get("enabled", True)))
    if not ok:
        raise ValidationError("Could not save preference.")
    return jsonify({"ok": True, "enabled": _ag.auto_gen_enabled()})


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
    from mcp import runtime
    runtime.shutdown_all()
    return jsonify({"ok": True})


@bp.get("/mcp/tools")
def mcp_tools_route():
    from mcp import runtime
    return jsonify({"tools": runtime.all_tools()})


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
        from system.autostart import is_enabled
        return jsonify({"enabled": is_enabled()})
    except Exception as exc:
        return jsonify({"enabled": False, "error": str(exc)[:120]})


@bp.post("/autostart/enable")
def autostart_enable():
    try:
        from system.autostart import enable
        ok = enable()
        return jsonify({"ok": ok, "enabled": ok})
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
    f = int(d.get("formality", 50))
    h = int(d.get("humor", 50))
    v = int(d.get("verbosity", 50))
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

    # Skip skills for purely conversational input
    from ai.self_awareness import is_conversational
    skill_reply = None
    if not is_conversational(text):
        skill_reply = dispatch_skill(text)
    if skill_reply:
        def s():
            yield f"data: {json.dumps({'delta': skill_reply, 'source': 'skill'})}\n\n"
            yield "data: [DONE]\n\n"
        speak_async(skill_reply)
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
                speak_async(_handled)
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
            speak_async(_prompt)

            def _sp():
                yield f"data: {json.dumps({'delta': _prompt, 'source': 'auto_skill'})}\n\n"
                yield "data: [DONE]\n\n"
            return Response(_sp(), mimetype="text/event-stream", headers={
                "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
                "Connection": "keep-alive"})

    route = "reasoning" if needs_reasoning(text) else "fast"

    store = get_store()
    client = get_client()
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
                speak_async(full)
                extract_memory_async(text, full)
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
