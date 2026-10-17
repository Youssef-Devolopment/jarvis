"""Real MCP runtime — launches stdio MCP servers and manages their tools."""
from __future__ import annotations

import asyncio
import os
import shutil
import threading
from contextlib import contextmanager as _contextmanager

from logger import get_logger
from mcp.manager import all_servers

log = get_logger(__name__)


def _find_sdk_base() -> str:
    """Site-packages directory that holds the real MCP SDK."""
    import site
    from pathlib import Path as _P
    for base in site.getsitepackages():
        try:
            cand = _P(base) / "mcp" / "__init__.py"
            if cand.is_file() and (cand.parent / "client").is_dir():
                return str(_P(base))
        except Exception:
            continue
    raise ImportError("mcp SDK not installed")


@_contextmanager
def _sdk_path():
    """Make the site-packages SDK win `import mcp` for the duration.

    Our own package is named mcp/, so the SDK's site dir is moved to
    the FRONT of sys.path while we import it. Entries are never
    removed: sys.path is global to the process, so deleting the
    project root raced concurrent imports in other threads (desktop
    boot vs Flask's first import — "No module named 'routes'").
    """
    import sys
    from pathlib import Path as _P

    sdk_base = _find_sdk_base()
    saved = sys.path[:]

    def _same_dir(p):
        try:
            return _P(p or ".").resolve() == _P(sdk_base)
        except Exception:
            return False

    sys.path = [sdk_base] + [p for p in saved if not _same_dir(p)]
    try:
        yield sdk_base
    finally:
        sys.path = saved


def _sdk():
    """Import the real MCP SDK despite our local mcp/ shadow.

    Evict the local mcp modules from sys.modules, import the SDK with
    _sdk_path() active (site dir first, no entries removed), then
    restore everything. Already-bound names (manager, runtime) are
    unaffected.

    The surgery touches process-global import state, so it runs ONCE
    per process and the result is cached: every server spawn used to
    reopen the window, and a boot-time Flask import landing inside it
    died with "cannot import name 'all_servers' from 'mcp'". Call
    prewarm() on the main thread before background threads spread to
    close even that single window.

    Returns (ClientSession, StdioServerParameters, stdio_client,
    TextContent). Raises ImportError when the SDK is missing.
    """
    global _sdk_cache
    if _sdk_cache is not None:
        if _sdk_cache is _SDK_FAILED:
            raise ImportError("mcp package not installed")
        return _sdk_cache
    with _sdk_lock:
        if _sdk_cache is not None:
            if _sdk_cache is _SDK_FAILED:
                raise ImportError("mcp package not installed")
            return _sdk_cache
        try:
            _sdk_cache = _sdk_uncached()
        except ImportError:
            _sdk_cache = _SDK_FAILED
            raise
        return _sdk_cache


def prewarm() -> bool:
    """Import the real MCP SDK now, on the calling thread — call on
    the main thread before background threads spread (both entry
    points do), so the single import-state surgery never races a
    concurrent local import. Never raises; True when the SDK loaded.
    """
    try:
        _sdk()
        log.info("MCP SDK prewarmed")
        return True
    except Exception as exc:
        log.debug("MCP SDK prewarm skipped: %s", exc)
        return False


_sdk_cache = None
_sdk_lock = threading.Lock()
_SDK_FAILED = object()


def _sdk_uncached():
    """One real surgery run. See _sdk() for why this executes once."""
    import sys

    saved_modules = {k: v for k, v in sys.modules.items()
                     if k == "mcp" or k.startswith("mcp.")}
    for k in saved_modules:
        del sys.modules[k]
    try:
        with _sdk_path():
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp.types import TextContent
        return ClientSession, StdioServerParameters, stdio_client, TextContent
    finally:
        sys.modules.update(saved_modules)


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

async def _close_quietly(*cms) -> None:
    """Best-effort __aexit__ for half-open MCP context managers.

    A failed handshake must not leave the child process (and its
    pipes) running, so callers tear down whatever came up.
    """
    for cm in cms:
        if cm is None:
            continue
        try:
            await cm.__aexit__(None, None, None)
        except Exception:
            pass


async def _start_server(server: dict) -> dict | None:
    """Launch an MCP server, list its tools, return a handle dict."""
    try:
        ClientSession, StdioServerParameters, stdio_client, _ = _sdk()
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

    transport_cm = session_cm = None
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
                # mcp SDK 2.x renamed inputSchema -> input_schema
                "input_schema": (getattr(t, "input_schema", None)
                                 or getattr(t, "inputSchema", None)
                                 or {}),
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
        # Close whatever came up so a failed handshake never leaves
        # the child process running (and does not leak its pipes).
        await _close_quietly(session_cm, transport_cm)
        return None


def _close_handle_blocking(loop, handle: dict | None) -> None:
    """Close a handle's context managers on the loop they came from."""
    if not handle or loop is None or loop.is_closed():
        return
    try:
        loop.run_until_complete(
            _close_quietly(handle.get("session_cm"),
                           handle.get("transport_cm")))
    except Exception:
        pass


def _start_in_loop(server: dict, timeout: float = 45.0) -> dict | None:
    """Run _start_server in a fresh event loop inside a thread.

    The join is bounded. A server slower than `timeout` is reported
    failed AND flagged abandoned, so when its thread eventually
    finishes it closes its own handle — otherwise a slow-but-live
    server would linger as an unreachable child process that nobody
    can call and nothing ever stops (they pile up across boots).
    """
    box: dict = {}

    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        handle = None
        try:
            handle = loop.run_until_complete(_start_server(server))
        except Exception as exc:
            log.exception("MCP startup thread failed: %s", exc)
        if box.get("abandoned"):
            _close_handle_blocking(loop, handle)
            try:
                loop.close()
            except Exception:
                pass
            return
        box["value"] = handle
        if handle:
            box["loop"] = loop       # keep loop alive so session stays usable
        else:
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        box["abandoned"] = True
        log.warning("MCP '%s' startup exceeded %.0fs; abandoning",
                    server.get("name"), timeout)
        # Race: the thread may finish between the timeout and the
        # flag. Give it a moment, then claim and close anything it
        # managed to store before it saw the flag.
        t.join(timeout=3)
        if not t.is_alive() and box.get("value"):
            _close_handle_blocking(box.get("loop"), box["value"])
            box.pop("value", None)
        return None
    return box.get("value")


def start_server(name: str, attempts: int = 2) -> bool:
    """Start a specific MCP server by name.

    stdio servers occasionally die during the handshake (a cold npx
    fetch, a transient failure on a loaded box), so a failed attempt
    is retried once before the server is reported down.
    """
    with _lock:
        if name in _servers and _servers[name]:
            return True
        srv = next((s for s in all_servers() if s.get("name") == name), None)
        if not srv:
            return False
        if not srv.get("enabled", True):
            return False
        for attempt in range(1, max(1, attempts) + 1):
            handle = _start_in_loop(srv)
            if handle:
                _servers[name] = handle
                return True
            if attempt < attempts:
                log.warning("MCP '%s' failed to start; retrying (%d/%d)",
                            name, attempt, attempts)
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


_tools_cache: list = []


def tools_snapshot(timeout: float = 1.0) -> list:
    """A copy of all_tools() that can never hang a request behind a
    slow server spawn (start_server holds the lock for the whole
    spawn, up to 45s per server).  Gives up after `timeout` and serves
    the last-known-good list instead — transient and honest.  Never
    raises."""
    global _tools_cache
    try:
        if not _lock.acquire(timeout=timeout):
            log.debug("MCP tools snapshot: lock busy, serving %d cached",
                      len(_tools_cache))
            return list(_tools_cache)
        try:
            fresh = []
            for sname, h in _servers.items():
                if not h:
                    continue
                for t in h["tools"]:
                    fresh.append({
                        "server": sname,
                        "name": t["name"],
                        "description": t["description"],
                        "input_schema": t["input_schema"],
                        "full_name": f"mcp__{sname}__{t['name']}",
                    })
            _tools_cache = fresh
            return list(fresh)
        finally:
            _lock.release()
    except Exception as exc:
        log.debug("MCP tools snapshot failed (%s), serving %d cached",
                  exc, len(_tools_cache))
        return list(_tools_cache)


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

    # Run in the same loop the server was created in. That loop is
    # idle (not running) after startup, so drive it directly; only
    # use run_coroutine_threadsafe when another thread runs it.
    loop = h.get("loop")
    if loop is not None and not loop.is_closed():
        if loop.is_running():
            fut = asyncio.run_coroutine_threadsafe(_call(), loop)
            try:
                fut.result(timeout=timeout)
            except Exception as exc:
                return f"Tool timeout: {str(exc)[:120]}"
        else:
            try:
                loop.run_until_complete(asyncio.wait_for(_call(), timeout))
            except Exception as exc:
                return f"Tool timeout: {str(exc)[:120]}"
    else:
        # Fallback: new loop (may not work for stdio streams)
        new_loop = asyncio.new_event_loop()
        try:
            new_loop.run_until_complete(asyncio.wait_for(_call(), timeout))
        except Exception as exc:
            return f"Tool timeout: {str(exc)[:120]}"
        finally:
            new_loop.close()

    return result_box.get("value", "(no output)")


def is_running(name: str) -> bool:
    """True when the named server has a live handle."""
    with _lock:
        return bool(_servers.get(name))


def running_names() -> list:
    with _lock:
        return [n for n, h in _servers.items() if h]


def stop_server(name: str) -> bool:
    """Stop ONE running server (config stays). Returns True if it was up."""
    with _lock:
        h = _servers.pop(name, None)
    if not h:
        return False
    try:
        loop = h.get("loop")

        async def _close():
            await h["session_cm"].__aexit__(None, None, None)
            await h["transport_cm"].__aexit__(None, None, None)

        if loop is not None and not loop.is_closed():
            if loop.is_running():
                fut = asyncio.run_coroutine_threadsafe(_close(), loop)
                try:
                    fut.result(timeout=10)
                except Exception:
                    pass
            else:
                loop.run_until_complete(asyncio.wait_for(_close(), 10))
        log.info("MCP '%s' stopped", name)
        return True
    except Exception as exc:
        log.debug("MCP stop '%s' failed: %s", name, exc)
        return True        # handle already dropped — treated as stopped


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
