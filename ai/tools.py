from __future__ import annotations
from ai import search_agent, headless_browser, app_manager
from ai import tools_fs, tools_terminal
from memory import context as ctx_tracker
from logger import get_logger

log = get_logger(__name__)

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "remember_fact",
        "description": "Store a durable fact about the user for future sessions.",
        "parameters": {"type": "object",
                       "properties": {"fact": {"type": "string"},
                                      "category": {"type": "string"}},
                       "required": ["fact"]}}},
    {"type": "function", "function": {
        "name": "switch_mood",
        "description": "Switch JARVIS mood: instant, thinking, deep, coding, creative, tutor, fast.",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "read_own_code",
        "description": "Read one of JARVIS own source files.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "deep_search",
        "description": "Research a question thoroughly across multiple web sources with citations. Slower than fast_search but more reliable.",
        "parameters": {"type": "object",
                       "properties": {"question": {"type": "string"}},
                       "required": ["question"]}}},
    {"type": "function", "function": {
        "name": "silent_browse",
        "description": "Open a URL in an INVISIBLE browser (no window).",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string"}},
                       "required": ["url"]}}},
    {"type": "function", "function": {
        "name": "silent_search",
        "description": "Search Google in the INVISIBLE browser.",
        "parameters": {"type": "object",
                       "properties": {"query": {"type": "string"},
                                      "max_results": {"type": "integer"}},
                       "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "silent_read",
        "description": "Read visible text from the invisible browser page.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "silent_click",
        "description": "Click a link in the invisible browser.",
        "parameters": {"type": "object",
                       "properties": {"text": {"type": "string"}},
                       "required": ["text"]}}},
    {"type": "function", "function": {
        "name": "fs_read",
        "description": "Read a file's contents.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "fs_write",
        "description": "Write (create/overwrite) a file. Overwrites back up first.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "fs_append",
        "description": "Append content to a file.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"},
                                      "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "fs_list",
        "description": "List files in a directory.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "fs_search",
        "description": "Search for files by name pattern.",
        "parameters": {"type": "object",
                       "properties": {"pattern": {"type": "string"},
                                      "root": {"type": "string"}},
                       "required": ["pattern"]}}},
    {"type": "function", "function": {
        "name": "fs_delete",
        "description": "Delete a file/folder (backup saved first).",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "fs_mkdir",
        "description": "Create a directory.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "term_run",
        "description": "Run a safe shell command (git, python, pip, dir, etc.).",
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string"},
                                      "timeout": {"type": "integer"}},
                       "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "term_python",
        "description": "Run inline Python code.",
        "parameters": {"type": "object",
                       "properties": {"code": {"type": "string"},
                                      "timeout": {"type": "integer"}},
                       "required": ["code"]}}},
    {"type": "function", "function": {
        "name": "list_open_apps",
        "description": "List all open windows on the user's computer.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "focus_app",
        "description": "Bring a window to the foreground.",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "launch_app",
        "description": "Launch a desktop app (notepad, calculator, vs code, chrome).",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "read_screen",
        "description": "Read text visible on the user's screen (OCR). Use when asked what's on screen or to read an error.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "win_click",
        "description": "Click a named button/control inside a window (native UI control, Code Mode gated).",
        "parameters": {"type": "object",
                       "properties": {"window": {"type": "string"},
                                      "control": {"type": "string"}},
                       "required": ["window", "control"]}}},
    {"type": "function", "function": {
        "name": "win_type",
        "description": "Type text into a named field inside a window (Code Mode gated).",
        "parameters": {"type": "object",
                       "properties": {"window": {"type": "string"},
                                      "control": {"type": "string"},
                                      "text": {"type": "string"}},
                       "required": ["window", "control", "text"]}}},
    {"type": "function", "function": {
        "name": "folder_watch",
        "description": "Watch a folder; JARVIS flags new files as they land.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "folder_unwatch",
        "description": "Stop watching folders (one path, or all if empty).",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {
        "name": "computer_run",
        "description": "Run a computer task via Open Interpreter (writes code and runs it; asks approval for risky steps). Prefer small direct tools for one-liners.",
        "parameters": {"type": "object",
                       "properties": {"goal": {"type": "string"},
                                      "timeout": {"type": "integer"}},
                       "required": ["goal"]}}},
    {"type": "function", "function": {
        "name": "open_url",
        "description": "Open ANY url as a real tab in the user's browser (shortcuts, domains, or full links).",
        "parameters": {"type": "object",
                       "properties": {"url": {"type": "string"}},
                       "required": ["url"]}}},
]


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
            from skills.screen_ocr import read_screen as _rs
            return _rs()
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
