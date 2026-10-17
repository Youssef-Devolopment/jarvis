"""routes.api_chat — the /command streaming turn."""
from routes._common import (
    TOOL_SCHEMAS,
    AIError,
    ConfigError,
    Response,
    ValidationError,
    _speak_quiet,
    bp,
    dispatch_skill,
    extract_memory_async,
    filtered_schemas,
    get_client,
    get_store,
    json,
    log,
    needs_reasoning,
    outcomes,
    request,
)


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

    # Tool-consent verdicts ("allow 3" / "deny 3") resolve a parked
    # agent-loop request before anything else can claim the turn.
    if not is_conversational(text):
        try:
            from ai import approvals as _appr
            _decided = _appr.handle_approval_text(text)
        except Exception:
            _decided = None
        if _decided:
            def _ca():
                yield f"data: {json.dumps({'delta': _decided, 'source': 'consent'})}\n\n"
                yield "data: [DONE]\n\n"
            try:
                storeA = get_store()
                storeA.messages_for(sid, text)
                storeA.record_reply(sid, _decided)
            except Exception:
                pass
            _speak_quiet(_decided)
            return Response(_ca(), mimetype="text/event-stream", headers={
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

    # Sub-agents: a multi-part question fans out to the parallel pool
    # first (plan -> run -> merge). Gated by the subagents_enabled
    # pref (staged rollout flag — off skips the pool entirely). A
    # failed pool never surfaces — the normal single loop below
    # answers instead.
    want_agents = False
    if not is_conversational(text):
        try:
            from memory import get_pref
            _agents_on = bool(get_pref("subagents_enabled", True))
        except Exception:
            _agents_on = True
        if _agents_on:
            try:
                want_agents = bool(client.should_use_agents(text))
            except Exception:
                want_agents = False

    def generate():
        collected = []
        yield f"data: {json.dumps({'route': route})}\n\n"
        try:
            if want_agents:
                yield f"data: {json.dumps({'status': 'Consulting sub-agents…'})}\n\n"
                try:
                    from ai import agents as _agents
                    _ares = _agents.run(text)
                except Exception as exc:
                    log.warning("Sub-agents failed: %s", exc)
                    _ares = {"ok": False}
                _aanswer = (_ares.get("answer") or "").strip() \
                    if _ares.get("ok") else ""
                if _aanswer:
                    if _ares.get("mode") == "parallel":
                        _astat = (f"{_ares.get('ok_tasks', 0)}/"
                                  f"{_ares.get('tasks', 0)} sub-tasks answered")
                        yield f"data: {json.dumps({'status': _astat})}\n\n"
                    collected.append(_aanswer)
                    yield f"data: {json.dumps({'delta': _aanswer, 'source': 'llm'})}\n\n"
                else:
                    yield f"data: {json.dumps({'status': 'Sub-agents came up empty — answering directly'})}\n\n"
            if not collected:
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
                    elif kind == "status":
                        # informational only — never collected, stored,
                        # spoken or rendered into the reply body
                        yield f"data: {json.dumps({'status': payload})}\n\n"
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


