"""Real MCP runtime — launches stdio MCP servers and manages their tools."""
from __future__ import annotations
import asyncio
import os
import shutil
import threading
import time

from logger import get_logger
from mcp.manager import all_servers

log = get_logger(__name__)

# Per-server state
_servers: dict[str, dict] = {}
_lock = threading.Lock()


def _find_npx() -> str | None:
    """Locate npx executable on Windows."""
    for name in ("npx.cmd", "npx", "npx.exe"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _build_env(server: dict) -> dict:
    """Merge env vars for the MCP subprocess."""
    env = dict(os.environ)
    env.update(server.get("env") or {})
    env["ANONYMIZED_TELEMETRY"] = "false"
    return env


def _resolve_command(server: dict) -> tuple[str, list[str]] | None:
    """Resolve the command + args for a server config."""
    cmd = (server.get("command") or "").strip()
    args = server.get("args") or []
    if not cmd:
        return None
    if cmd == "npx":
        npx = _find_npx()
        if not npx:
            log.error("npx not found on PATH for server '%s'", server.get("name"))
            return None
        return npx, list(args)
    return cmd, list(args)


# ---------- one-time setup per server ----------

async def _start_server(server: dict) -> dict | None:
    """Launch an MCP server, list its tools, return a handle dict."""
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError:
        log.error("mcp package not installed. Run: pip install mcp")
        return None

    resolved = _resolve_command(server)
    if not resolved:
        return None
    cmd, args = resolved

    params = StdioServerParameters(
        command=cmd,
        args=args,
        env=_build_env(server),
    )

    try:
        # Keep the client context alive across calls
        transport_cm = stdio_client(params)
        read, write = await transport_cm.__aenter__()
        session_cm = ClientSession(read, write)
        session = await session_cm.__aenter__()
        await session.initialize()

        tools_resp = await session.list_tools()
        tools = []
        for t in (tools_resp.tools or []):
            tools.append({
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema or {},
            })

        log.info("MCP '%s' started with %d tools",
                 server.get("name"), len(tools))

        return {
            "session": session,
            "transport_cm": transport_cm,
            "session_cm": session_cm,
            "tools": tools,
            "loop": asyncio.get_event_loop(),
        }
    except Exception as exc:
        log.exception("Failed to start MCP '%s': %s", server.get("name"), exc)
        return None


def _start_in_loop(server: dict) -> dict | None:
    """Run _start_server in a fresh event loop inside a thread."""
    result: dict = {}
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result["value"] = loop.run_until_complete(_start_server(server))
            # Keep loop alive so session stays usable
            result["loop"] = loop
        except Exception as exc:
            log.exception("MCP startup thread failed: %s", exc)
    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=45)
    return result.get("value")


def start_server(name: str) -> bool:
    """Start a specific MCP server by name."""
    with _lock:
        if name in _servers and _servers[name]:
            return True
        srv = next((s for s in all_servers() if s.get("name") == name), None)
        if not srv:
            return False
        if not srv.get("enabled", True):
            return False
        handle = _start_in_loop(srv)
        if handle:
            _servers[name] = handle
            return True
        return False


def start_all() -> dict:
    """Start every enabled MCP server. Returns summary."""
    started, failed = [], []
    for srv in all_servers():
        if not srv.get("enabled", True):
            continue
        name = srv.get("name", "?")
        if start_server(name):
            started.append(name)
        else:
            failed.append(name)
    return {"started": started, "failed": failed}


def all_tools() -> list[dict]:
    """Return every tool across every running MCP server."""
    out = []
    with _lock:
        for sname, h in _servers.items():
            if not h:
                continue
            for t in h["tools"]:
                out.append({
                    "server": sname,
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["input_schema"],
                    "full_name": f"mcp__{sname}__{t['name']}",
                })
    return out


def call_tool(server_name: str, tool_name: str, arguments: dict,
              timeout: float = 60.0) -> str:
    """Invoke an MCP tool. Returns a text result."""
    with _lock:
        h = _servers.get(server_name)
    if not h:
        return f"MCP server '{server_name}' is not running."

    result_box: dict = {}

    async def _call():
        try:
            from mcp.types import TextContent
            resp = await h["session"].call_tool(tool_name, arguments=arguments)
            parts = []
            for c in (resp.content or []):
                # TextContent -> .text, others -> str
                txt = getattr(c, "text", None)
                if txt:
                    parts.append(txt)
                else:
                    parts.append(str(c))
            result_box["value"] = "\n".join(parts) if parts else "(no output)"
        except Exception as exc:
            log.exception("MCP tool call failed: %s", exc)
            result_box["value"] = f"Tool error: {str(exc)[:200]}"

    # Run in the same loop the server was created in
    loop = h.get("loop")
    if loop and loop.is_running() is False:
        fut = asyncio.run_coroutine_threadsafe(_call(), loop)
        try:
            fut.result(timeout=timeout)
        except Exception as exc:
            return f"Tool timeout: {str(exc)[:120]}"
    else:
        # Fallback: new loop (may not work for stdio streams)
        new_loop = asyncio.new_event_loop()
        try:
            new_loop.run_until_complete(_call())
        finally:
            new_loop.close()

    return result_box.get("value", "(no output)")


def shutdown_all():
    with _lock:
        for name, h in list(_servers.items()):
            try:
                loop = h.get("loop")
                if loop:
                    asyncio.run_coroutine_threadsafe(
                        h["session_cm"].__aexit__(None, None, None), loop)
                    asyncio.run_coroutine_threadsafe(
                        h["transport_cm"].__aexit__(None, None, None), loop)
            except Exception as exc:
                log.debug("MCP shutdown '%s' failed: %s", name, exc)
        _servers.clear()
