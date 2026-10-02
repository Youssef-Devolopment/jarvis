"""Native JARVIS MCP server — stdio / JSON-RPC 2.0 (newline-delimited).

Exposes JARVIS to any MCP host (VS Code, Claude Desktop, Cursor, ...)
as official tools + resources:

  tools:
    jarvis_skills      list the 117+ hot-reloadable skills
    jarvis_command     natural-language command -> running JARVIS
    jarvis_terminal    sandboxed terminal (same guards as the dashboard)
    jarvis_memory      list / search / add / forget persistent facts
    jarvis_obsidian    clip + search notes in the Obsidian vault
    jarvis_ports       port sentinel: list listeners / kill a pid
    jarvis_screen_ocr  read text from the current screen (vision)

  resources:
    jarvis://skills         skill registry snapshot
    jarvis://memory/facts   all persistent memory facts (JSON)
    jarvis://vault/notes    recent Obsidian notes (JSON)
    jarvis://system/info    runtime info (version, model, mood, ...)

Run:   .venv\\Scripts\\python.exe -m mcp.server      (cwd = project root)
Protocol: MCP stdio transport — one JSON-RPC message per line on
stdout; ALL logging goes to stderr so it can never corrupt the stream.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

SERVER_NAME = "jarvis"
PROTOCOL_FALLBACK = "2024-11-05"


def _log(msg: str) -> None:
    sys.stderr.write(f"[jarvis-mcp] {msg}\n")
    sys.stderr.flush()


def _version() -> str:
    try:
        from config import VERSION
        return VERSION
    except Exception:
        return "0.0.0"


# ---------------------------------------------------------------- helpers
def _http_get(path: str, timeout: int = 15) -> dict:
    import urllib.request
    from config import get_settings
    s = get_settings()
    with urllib.request.urlopen(
            f"http://{s.host}:{s.port}/api{path}", timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _command_reply(text: str) -> str:
    """POST /api/command and stitch the SSE stream into one reply."""
    import urllib.request
    from config import get_settings
    from system.overlay import stitch_sse
    s = get_settings()
    req = urllib.request.Request(
        f"http://{s.host}:{s.port}/api/command",
        data=json.dumps({"text": text, "session": "mcp"}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return stitch_sse(r) or "(no reply)"


# ---------------------------------------------------------------- tools
TOOLS = [
    {
        "name": "jarvis_skills",
        "description": "List every installed JARVIS skill (hot-reloadable, "
                       "harness-modifiable). Set include_descriptions=true "
                       "for one-line docs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "include_descriptions": {"type": "boolean", "default": False}
            },
        },
    },
    {
        "name": "jarvis_command",
        "description": "Send a natural-language command to the running "
                       "JARVIS assistant and get its reply (voice/mood/"
                       "skills aware). JARVIS must be running.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The command"},
            },
            "required": ["text"],
        },
    },
    {
        "name": "jarvis_terminal",
        "description": "Run a shell command inside the JARVIS sandbox "
                       "(project cwd, destructive commands blocked).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "default": 30},
            },
            "required": ["command"],
        },
    },
    {
        "name": "jarvis_memory",
        "description": "Persistent memory: list, search, add or forget "
                       "facts JARVIS knows about the user.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": ["list", "search", "add", "forget"]},
                "query": {"type": "string"},
                "fact": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "jarvis_obsidian",
        "description": "Obsidian vault bridge: clip an idea as a note, "
                       "list recent notes, or search them.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string",
                           "enum": ["list", "search", "save"]},
                "content": {"type": "string"},
                "query": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "jarvis_ports",
        "description": "Port sentinel: list listening TCP ports (with "
                       "process names) or kill a process holding a port.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["list", "kill"]},
                "pid": {"type": "integer"},
                "port": {"type": "integer"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "jarvis_screen_ocr",
        "description": "Omniscience: capture the screen and extract all "
                       "visible text (vision model). Use for 'fix this "
                       "error' style questions without copy-pasting.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string",
                             "description": "What to extract / analyze"},
            },
        },
    },
]


def call_tool(name: str, args: dict) -> str:
    """Dispatch a tools/call. Returns the text payload; raises on errors."""
    args = args or {}
    if name == "jarvis_skills":
        from skills import all_skills
        skills = all_skills()
        if args.get("include_descriptions"):
            return "\n".join(
                f"- {s.name}: {getattr(s, 'description', '') or ''}".strip()
                for s in skills)
        return ", ".join(s.name for s in skills)

    if name == "jarvis_command":
        text = (args.get("text") or "").strip()
        if not text:
            raise ValueError("'text' is required")
        return _command_reply(text)

    if name == "jarvis_terminal":
        from ai import tools_terminal
        cmd = (args.get("command") or "").strip()
        if not cmd:
            raise ValueError("'command' is required")
        try:
            timeout = max(1, min(120, int(args.get("timeout", 30))))
        except Exception:
            timeout = 30
        return tools_terminal.term_run(cmd, timeout)

    if name == "jarvis_memory":
        import memory
        action = (args.get("action") or "list").lower()
        if action == "list":
            facts = memory.all_facts()
            return json.dumps(facts, ensure_ascii=False, indent=1)[:60000]
        if action == "search":
            q = (args.get("query") or "").strip()
            if not q:
                raise ValueError("'query' is required")
            hits = memory.recall(q, limit=10)
            return json.dumps(hits, ensure_ascii=False, indent=1)[:60000]
        if action == "add":
            fact = (args.get("fact") or "").strip()
            if not fact:
                raise ValueError("'fact' is required")
            memory.remember(fact)
            return f"stored: {fact}"
        if action == "forget":
            q = (args.get("query") or "").strip()
            if not q:
                raise ValueError("'query' is required")
            n = memory.forget(q)
            return f"forgot {n} fact(s)"
        raise ValueError(f"unknown action: {action}")

    if name == "jarvis_obsidian":
        from ai import obsidian
        action = (args.get("action") or "list").lower()
        if not obsidian.is_available():
            return "Obsidian vault not configured (set OBSIDIAN_VAULT)."
        if action == "save":
            content = (args.get("content") or "").strip()
            if not content:
                raise ValueError("'content' is required")
            return "saved: " + obsidian.save_note(content)
        if action == "search":
            q = (args.get("query") or "").strip()
            if not q:
                raise ValueError("'query' is required")
            return json.dumps(obsidian.search_notes(q, limit=10),
                              ensure_ascii=False, indent=1)[:60000]
        return json.dumps(obsidian.list_notes(limit=10),
                          ensure_ascii=False, indent=1)[:60000]

    if name == "jarvis_ports":
        from ai import ports
        action = (args.get("action") or "list").lower()
        if action == "kill":
            r = ports.kill_listener(args.get("pid", 0),
                                    args.get("port", 0) or 0)
            return json.dumps(r, ensure_ascii=False)
        items = ports.list_listeners()
        return json.dumps(items[:80], ensure_ascii=False, indent=1)[:60000]

    if name == "jarvis_screen_ocr":
        from ai import screen_text
        q = (args.get("question") or "").strip() or None
        return screen_text.extract_text(q) if q else screen_text.extract_text()

    raise ValueError(f"unknown tool: {name}")


# ------------------------------------------------------------ resources
RESOURCES = [
    {"uri": "jarvis://skills", "name": "JARVIS skills",
     "description": "All installed skills", "mimeType": "text/plain"},
    {"uri": "jarvis://memory/facts", "name": "Memory facts",
     "description": "Everything JARVIS remembers", "mimeType": "application/json"},
    {"uri": "jarvis://vault/notes", "name": "Obsidian notes",
     "description": "Recent notes in the vault", "mimeType": "application/json"},
    {"uri": "jarvis://system/info", "name": "System info",
     "description": "Runtime version / model / mood", "mimeType": "application/json"},
]


def read_resource(uri: str) -> str:
    if uri == "jarvis://skills":
        from skills import all_skills
        return "\n".join(s.name for s in all_skills())
    if uri == "jarvis://memory/facts":
        import memory
        return json.dumps(memory.all_facts(), ensure_ascii=False, indent=1)
    if uri == "jarvis://vault/notes":
        from ai import obsidian
        if not obsidian.is_available():
            return "[]"
        return json.dumps(obsidian.list_notes(limit=20),
                          ensure_ascii=False, indent=1)
    if uri == "jarvis://system/info":
        try:
            return json.dumps(_http_get("/info"), ensure_ascii=False, indent=1)
        except Exception as exc:
            return json.dumps({"version": _version(), "error": str(exc)})
    raise ValueError(f"unknown uri: {uri}")


# ---------------------------------------------------------- json-rpc io
def _reply(msg_id, result=None, error=None) -> dict:
    m = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        m["error"] = error
    else:
        m["result"] = result
    return m


def handle(msg: dict) -> dict | None:
    """Handle one JSON-RPC message. Returns a reply dict or None (notif)."""
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}
    is_notification = "id" not in msg

    try:
        if method == "initialize":
            pv = params.get("protocolVersion")
            if not isinstance(pv, str) or not pv:
                pv = PROTOCOL_FALLBACK
            return _reply(msg_id, {
                "protocolVersion": pv,
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False, "listChanged": False},
                },
                "serverInfo": {"name": SERVER_NAME,
                               "version": _version()},
                "instructions": "JARVIS personal AI OS. Use jarvis_command "
                                "for natural language, jarvis_skills to "
                                "discover capabilities, jarvis_memory for "
                                "persistent facts.",
            })

        if is_notification:          # initialized / cancelled / etc.
            return None

        if method == "ping":
            return _reply(msg_id, {})

        if method == "tools/list":
            return _reply(msg_id, {"tools": TOOLS})

        if method == "tools/call":
            name = params.get("name")
            try:
                text = call_tool(name, params.get("arguments") or {})
                return _reply(msg_id, {
                    "content": [{"type": "text", "text": str(text)}],
                    "isError": False,
                })
            except Exception as exc:
                return _reply(msg_id, {
                    "content": [{"type": "text", "text": f"error: {exc}"}],
                    "isError": True,
                })

        if method == "resources/list":
            return _reply(msg_id, {"resources": RESOURCES})

        if method == "resources/templates/list":
            return _reply(msg_id, {"resourceTemplates": []})

        if method == "resources/read":
            uri = params.get("uri")
            try:
                text = read_resource(uri)
                return _reply(msg_id, {"contents": [
                    {"uri": uri, "mimeType": "text/plain", "text": text}]})
            except Exception as exc:
                return _reply(msg_id, error={
                    "code": -32002, "message": str(exc)})

        if method == "prompts/list":
            return _reply(msg_id, {"prompts": []})

        return _reply(msg_id, error={
            "code": -32601, "message": f"method not found: {method}"})
    except Exception as exc:
        _log(f"handler error on {method}: {exc}")
        if is_notification:
            return None
        return _reply(msg_id, error={"code": -32603, "message": str(exc)})


def main() -> int:
    _log(f"stdio server up (v{_version()}, pid {__import__('os').getpid()})")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except Exception as exc:
            _log(f"bad json: {exc}")
            out = _reply(None, error={"code": -32700,
                                      "message": "parse error"})
            sys.stdout.write(json.dumps(out) + "\n")
            sys.stdout.flush()
            continue
        reply = handle(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()
    _log("stdin closed — exiting")
    return 0


if __name__ == "__main__":
    sys.exit(main())
