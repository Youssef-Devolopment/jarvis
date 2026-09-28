"""Tool dispatcher — routes tool calls to backend modules."""

from __future__ import annotations
import json
from logger import get_logger

# Import backends as before
from ai import search_agent, headless_browser, app_manager
from ai import tools_fs, tools_terminal
from ai import tool_schemas
from ai import reality_check
from ai import bridge
from memory import context as ctx_tracker
from memory import outcomes

log = get_logger(__name__)


def execute_tool(name: str, args: dict) -> str:
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
    """Generate OpenAI-style schemas for every MCP tool currently running."""
    try:
        from mcp import runtime
    except ImportError:
        return []
    out = []
    for t in runtime.all_tools():
        out.append({
            "type": "function",
            "function": {
                "name": t["full_name"],
                "description": f"[{t['server']}] {t['description']}"[:1000],
                "parameters": t["input_schema"] or {
                    "type": "object", "properties": {}},
            },
        })
    return out
