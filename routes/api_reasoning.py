"""routes.api_reasoning — council, outcomes/reality-check, agents, dream, research."""
from routes._common import (
    LEVEL_SPECS,
    Level,
    ValidationError,
    agents,
    bp,
    dream_mode,
    jsonify,
    outcomes,
    reality_check,
    request,
)


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


