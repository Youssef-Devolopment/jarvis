"""routes.api_skills — skills, auto-skills (drafts), app learner."""
from routes._common import (
    ValidationError,
    all_skills,
    bp,
    jsonify,
    request,
    toggle_skill,
)


# ---------- SKILLS ----------
@bp.get("/skills")
def skills_list():
    return jsonify({
        "skills": [
            {"name": sk.name, "description": sk.description, "enabled": sk.enabled}
            for sk in all_skills()
        ]
    })


@bp.get("/skills/match")
def skills_match():
    """Diagnostic: which skill patterns match a phrase, and which skill
    last actually answered. No handler runs — safe to call any time."""
    from skills.registry import last_match, match_only
    text = (request.args.get("text") or "").strip()
    if not text:
        raise ValidationError("Missing 'text'.",
                              detail="Pass ?text=your phrase.")
    out = {"text": text, "last": last_match()}
    out.update(match_only(text))
    return jsonify(out)


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


# ---------- APP LEARNER (autonomous skill generation) ----------
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


