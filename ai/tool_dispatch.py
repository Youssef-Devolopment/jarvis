"""Tool dispatcher — routes tool calls to backend modules."""

from __future__ import annotations

# Import backends as before
from ai import (
    app_manager,
    bridge,
    headless_browser,
    reality_check,
    search_agent,
    tool_schemas,
    tools_fs,
    tools_terminal,
)
from logger import get_logger
from memory import context as ctx_tracker
from memory import outcomes

log = get_logger(__name__)


_AUDIT_FAIL_PREFIXES = (
    "Tool error", "[error]", "[blocked]", "[refused]",
    "Unknown tool", "Invalid MCP tool name", "MCP server '",
    "Tool timeout", "Denied by user",
)


def _audit_ok(result: str) -> bool:
    return not str(result).startswith(_AUDIT_FAIL_PREFIXES)


def _coerce_arg(value, want: str):
    """Coerce an LLM-supplied arg to the schema type. Returns
    (ok, value). Strings stay strict; numbers/bools accept their
    obvious string forms ("30", "true")."""
    if want == "string":
        return (isinstance(value, str), value)
    if want == "integer":
        if isinstance(value, bool):
            return False, value
        if isinstance(value, int):
            return True, value
        if isinstance(value, str) and value.strip().lstrip("-").isdigit():
            return True, int(value.strip())
        return False, value
    if want == "number":
        if isinstance(value, bool):
            return False, value
        if isinstance(value, (int, float)):
            return True, value
        try:
            return True, float(str(value).strip())
        except (ValueError, TypeError):
            return False, value
    if want == "boolean":
        if isinstance(value, bool):
            return True, value
        if isinstance(value, str) and value.strip().lower() in (
                "true", "false"):
            return True, value.strip().lower() == "true"
        return False, value
    return True, value  # object/array/unknown: structural check skipped


def validate_tool_args(name: str, args: dict):
    """Validate args against the central TOOL_SCHEMAS entry. Returns
    (ok, args_or_error): on success a (possibly coerced) args dict,
    on failure an error string. MCP/unknown names skip strict checks
    (dict shape only) — their schemas live across the wire."""
    if not isinstance(args, dict):
        return False, f"Tool error: invalid arguments for {name}: not an object."
    if not isinstance(name, str) or name.startswith("mcp__"):
        return True, args
    try:
        entry = next(t for t in tool_schemas.TOOL_SCHEMAS
                     if t.get("function", {}).get("name") == name)
        params = entry.get("function", {}).get("parameters", {})
    except Exception:
        return True, args
    required = params.get("required", []) or []
    for key in required:
        if key not in args or args[key] is None:
            return False, (f"Tool error: invalid arguments for {name}: "
                           f"missing required '{key}'.")
    props = params.get("properties", {}) or {}
    clean = dict(args)
    for key, spec in props.items():
        if key not in clean or not isinstance(spec, dict):
            continue
        want = spec.get("type")
        if not want:
            continue
        ok, value = _coerce_arg(clean[key], want)
        if not ok:
            return False, (f"Tool error: invalid arguments for {name}: "
                           f"'{key}' must be {want}.")
        clean[key] = value
    return True, clean


def execute_tool(name: str, args: dict) -> str:
    """Single choke point for every agent tool call (chat loop, OS
    missions, consent verdicts, demos): validates args, runs the tool
    and lands one line in the shared audit trail. Same signature,
    never raises."""
    ok, checked = validate_tool_args(name, args)
    if not ok:
        try:
            from system import audit as _trail
            _trail.record(str(name), str(args or {})[:80], False,
                          "invalid arguments")
        except Exception:
            pass
        return checked
    try:
        out = _execute_tool(name, checked)
    except Exception as exc:  # backstop; the body guards itself too
        out = f"Tool error: {exc}"
    try:
        from logger import redact as _redact
        from system import audit as _trail
        _trail.record(str(name), _redact(str(checked or {}))[:80],
                      _audit_ok(out))
    except Exception:
        pass
    return out


def _execute_tool(name: str, args: dict) -> str:
    try:
        _brief = str(args)[:150] if args else ""
        ctx_tracker.log_event("action", f"{name} {_brief}")
    except Exception:
        pass
    try:
        if name == "remember_fact":
            from memory import remember
            fact = (args.get("fact") or "").strip()
            cat = (args.get("category") or "general").strip()
            if not fact: return "Error: empty fact."
            remember(fact, category=cat, source="tool")
            return f"Remembered: {fact}"
        if name == "switch_mood":
            from moods import set_mood
            m = set_mood(args.get("name") or "")
            if m:
                return f"Switched to {m.name} mood."
            return "Unknown mood."
        if name == "read_own_code":
            from harness import read_file
            p = (args.get("path") or "").strip()
            return read_file(p)[:4000]
        if name == "deep_search":
            return search_agent.deep_search(args.get("question", ""))
        if name == "silent_browse":
            return headless_browser.browse(args.get("url", ""))
        if name == "silent_search":
            return headless_browser.search_google(
                args.get("query", ""), int(args.get("max_results", 5)))
        if name == "silent_read":
            return headless_browser.read_page()
        if name == "silent_click":
            return headless_browser.click_link(args.get("text", ""))
        if name == "fs_read":
            r = tools_fs.fs_read(args.get("path", ""))
            ctx_tracker.log_event("file", f"read {args.get('path','')}")
            return r
        if name == "fs_write":
            r = tools_fs.fs_write(args.get("path", ""), args.get("content", ""))
            ctx_tracker.log_event("file", f"wrote {args.get('path','')}")
            return r
        if name == "fs_append":
            return tools_fs.fs_append(args.get("path", ""), args.get("content", ""))
        if name == "fs_list":
            return tools_fs.fs_list(args.get("path", "."))
        if name == "fs_search":
            return tools_fs.fs_search(args.get("pattern", ""), args.get("root", "."))
        if name == "fs_delete":
            return tools_fs.fs_delete(args.get("path", ""))
        if name == "fs_mkdir":
            return tools_fs.fs_mkdir(args.get("path", ""))
        if name == "fs_replace":
            r = tools_fs.fs_replace(args.get("path", ""),
                                    args.get("old", ""),
                                    args.get("new", ""),
                                    bool(args.get("replace_all", False)))
            ctx_tracker.log_event("file", f"edited {args.get('path','')}")
            return r
        if name == "term_run":
            _cmd = args.get("command", "")[:80]
            ctx_tracker.log_event("action", f"ran: {_cmd}")
            return tools_terminal.term_run(args.get("command", ""),
                                           int(args.get("timeout", 30)))
        if name == "term_python":
            return tools_terminal.term_python(args.get("code", ""),
                                              int(args.get("timeout", 30)))
        if name == "list_open_apps":
            return app_manager.list_windows()
        if name == "focus_app":
            r = app_manager.focus_window(args.get("name", ""))
            ctx_tracker.log_event("app", f"focused {args.get('name','')}")
            return r
        if name == "launch_app":
            r = app_manager.launch_app(args.get("name", ""))
            ctx_tracker.log_event("app", f"launched {args.get('name','')}")
            return r
        if name == "read_screen":
            from skills import dispatch as _dispatch
            return _dispatch("read text from screen") or "[screen_ocr failed]"
        if name == "win_click":
            from skills.win_target import win_click as _wc
            return _wc(args.get("window", ""), args.get("control", ""))
        if name == "win_type":
            from skills.win_target import win_type as _wt
            return _wt(args.get("window", ""), args.get("control", ""),
                       args.get("text", ""))
        if name == "folder_watch":
            from skills.folder_sentinel import watch as _w
            return _w(args.get("path", ""))
        if name == "folder_unwatch":
            from skills.folder_sentinel import unwatch as _uw
            return _uw(args.get("path", ""))
        if name == "computer_run":
            from system.interpreter_hand import run_goal as _rg
            r = _rg(args.get("goal", ""),
                    timeout=int(args.get("timeout", 120) or 120))
            if r.get("ok"):
                return (r.get("output") or "(done, no output)")[:2000]
            return f"Computer task failed: {r.get('error', 'unknown')[:200]}"
        if name == "open_url":
            from system import launch as _L
            out = _L.open_url(args.get("url", ""))
            return out or "Could not open that."
        if name == "outcome_stats":
            s = outcomes.stats()
            return (f"Outcomes: {s['total']} total, "
                    f"{s['accepted']} accepted, "
                    f"{s['rejected']} rejected, "
                    f"{s['pending']} pending.")
        if name == "reality_check_tool":
            r = reality_check.verify(
                args.get("question", ""), args.get("answer", ""))
            return (f"Checked: {r.get('checked')}, "
                    f"agree: {r.get('agree')}, "
                    f"confidence: {r.get('confidence')}%, "
                    f"note: {r.get('note', '')}")
        if name == "bridge_transfer":
            return bridge.transfer(
                args.get("source", ""),
                args.get("target", ""),
                args.get("action", "copy"))
        # MCP tool: name format is mcp__<server>__<tool>
        if name.startswith("mcp__"):
            parts = name.split("__", 2)
            if len(parts) == 3:
                from mcp import runtime
                server_name, tool_name = parts[1], parts[2]
                return runtime.call_tool(server_name, tool_name, args)
            return "Invalid MCP tool name."
        return f"Unknown tool: {name}"
    except Exception as exc:
        log.exception("Tool '%s' failed", name)
        return f"Tool error: {exc}"


def mcp_schemas() -> list:
    """OpenAI-style schemas for every running MCP tool.  Never raises:
    one sick server (bad entry, malformed schema, lock held by a spawn,
    runtime exploding) costs its tools, never the whole AI request.
    Output is sorted by name so the model sees a deterministic catalog
    no matter what order servers started in."""
    try:
        from mcp import runtime
        try:
            entries = runtime.tools_snapshot()
        except Exception:
            return []
    except ImportError:
        return []
    out = []
    for t in entries:
        try:
            if not isinstance(t, dict):
                continue
            server = t.get("server") or ""
            name = t.get("name") or ""
            full = t.get("full_name") or ""
            if not (isinstance(server, str) and server
                    and isinstance(name, str) and name
                    and isinstance(full, str) and full):
                continue
            desc = t.get("description") or ""
            if not isinstance(desc, str):
                desc = str(desc)
            params = t.get("input_schema") or {"type": "object",
                                               "properties": {}}
            if not isinstance(params, dict):
                params = {"type": "object", "properties": {}}
            out.append({
                "type": "function",
                "function": {
                    "name": full,
                    "description": f"[{server}] {desc}"[:1000],
                    "parameters": params,
                },
            })
        except Exception:
            continue
    out.sort(key=lambda s: s["function"]["name"])
    return out
