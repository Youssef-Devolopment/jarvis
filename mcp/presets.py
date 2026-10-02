"""MCP presets — one-click servers + Claude config import."""

from __future__ import annotations
import shutil
from logger import get_logger

log = get_logger(__name__)

# id, name, description, command, args, needs (env keys, informational)
PRESETS = [
    {"id": "filesystem", "name": "Filesystem",
     "description": "Read/write files in one folder. Set args to the folder.",
     "command": "npx", "args": "-y @modelcontextprotocol/server-filesystem",
     "needs": "folder path in args"},
    {"id": "sqlite", "name": "SQLite",
     "description": "Query a SQLite DB file. Set args to the .db path.",
     "command": "npx", "args": "-y @modelcontextprotocol/server-sqlite",
     "needs": "db file path in args"},
    {"id": "fetch", "name": "Fetch",
     "description": "Fetch URLs as text. No setup.",
     "command": "npx", "args": "-y @modelcontextprotocol/server-fetch",
     "needs": "nothing"},
    {"id": "memory", "name": "Memory",
     "description": "Persistent knowledge graph across sessions.",
     "command": "npx", "args": "-y @modelcontextprotocol/server-memory",
     "needs": "nothing"},
    {"id": "sequential-thinking", "name": "Sequential thinking",
     "description": "Step-by-step reasoning helper.",
     "command": "npx",
     "args": "-y @modelcontextprotocol/server-sequential-thinking",
     "needs": "nothing"},
    {"id": "github", "name": "GitHub",
     "description": "Repos, issues, PRs. Needs a token.",
     "command": "npx", "args": "-y @modelcontextprotocol/server-github",
     "needs": "GITHUB_PERSONAL_ACCESS_TOKEN env"},
    {"id": "brave-search", "name": "Brave search",
     "description": "Web search. Needs a key.",
     "command": "npx", "args": "-y @modelcontextprotocol/server-brave-search",
     "needs": "BRAVE_API_KEY env"},
    {"id": "puppeteer", "name": "Puppeteer",
     "description": "Headless browser pages.",
     "command": "npx", "args": "-y @modelcontextprotocol/server-puppeteer",
     "needs": "nothing"},
]


def list_presets() -> list:
    return [dict(p) for p in PRESETS]


def get_preset(pid: str) -> dict | None:
    pid = (pid or "").strip().lower()
    return next((p for p in PRESETS if p["id"] == pid), None)


def toolchain() -> dict:
    """What the machine can run MCP servers with."""
    return {"npx": bool(shutil.which("npx") or shutil.which("npx.cmd")),
            "node": bool(shutil.which("node")),
            "python": True}


def install_preset(pid: str, args: str = "", env: dict | None = None) -> dict:
    """One-click preset install. Returns the stored server entry."""
    from mcp.manager import add_server
    p = get_preset(pid)
    if not p:
        return {"error": f"unknown preset: {pid}"}
    final_args = (args or "").strip() or p["args"]
    entry = add_server(p["name"], p["command"], final_args)
    if isinstance(entry, dict) and entry.get("error"):
        return entry
    if env:
        entry["env"] = dict(env)
        from mcp.manager import all_servers
        items = all_servers()
        for s in items:
            if s.get("name") == entry.get("name"):
                s["env"] = dict(env)
        from mcp import manager as _m
        with _m._lock:
            _m._save(items)
    log.info("MCP preset installed: %s", p["id"])
    return {"ok": True, "server": entry, "needs": p["needs"]}


def import_claude_config(data: dict) -> dict:
    """Import Claude-style {"mcpServers": {name: {command, args, env}}}."""
    from mcp.manager import add_server
    if not isinstance(data, dict):
        return {"error": "config must be an object"}
    servers = data.get("mcpServers") or {}
    if not isinstance(servers, dict) or not servers:
        return {"error": "no mcpServers found"}
    added = []
    for name, spec in servers.items():
        if not isinstance(spec, dict) or not spec.get("command"):
            continue
        args = spec.get("args") or []
        entry = add_server(name, spec["command"],
                           " ".join(str(a) for a in args))
        if isinstance(entry, dict) and not entry.get("error"):
            if spec.get("env"):
                entry["env"] = dict(spec["env"])
            added.append(entry.get("name", name))
    return {"ok": True, "added": added}


def serve_config() -> dict:
    """How an MCP host should launch JARVIS's own native server.

    Returns ready-to-paste configs for Claude Desktop, VS Code and a
    raw command line. Uses the venv python.exe (never pythonw — hosts
    need real stdio).
    """
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    exe = Path(sys.executable).resolve()
    if exe.name.lower().startswith("pythonw"):
        sibling = exe.with_name("python.exe")
        if sibling.exists():
            exe = sibling
    args = ["-m", "mcp.server"]
    entry = {"command": str(exe), "args": args, "cwd": str(root)}
    return {
        "command": str(exe),
        "args": args,
        "cwd": str(root),
        "claude_config": {"mcpServers": {"jarvis": dict(entry)}},
        "vscode_config": {"servers": {"jarvis": {"type": "stdio", **entry}}},
        "cli": f'"{exe}" -m mcp.server   (cwd: {root})',
    }
