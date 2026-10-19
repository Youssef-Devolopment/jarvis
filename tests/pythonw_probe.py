"""Probe launched by tests/test_pythonw_smoke.py under real pythonw.exe.

Not a test module: `unittest discover` only collects `test*.py`, so this
file is inert on its own. It exists to run inside the interpreter the app
actually ships with on Windows, where there is no console:

    sys.stdout is None, sys.stderr is None

That is the condition DECISIONS #14 is about. The probe checks the fix
where in-process patching cannot: a grandchild process is started with the
handle returned by `mcp.runtime._errlog()`, writes a startup banner the way
an MCP server does, and must exit cleanly. The same grandchild started with
`stderr=None` must die - if it does not, this machine no longer reproduces
the bug and the guard is worthless.

There is no stdout to print to, so the verdict is written as JSON to the
path in JARVIS_PW_PROBE_OUT.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# A child that behaves like an MCP server logging its startup banner.
BANNER = "import sys; sys.stderr.write('probe banner\\n'); sys.stderr.flush()"


def _run_grandchild(stderr):
    return subprocess.run(
        [sys.executable, "-c", BANNER],
        stdout=subprocess.DEVNULL,
        stderr=stderr,
        timeout=30,
    ).returncode


async def _mcp_roundtrip(runtime):
    """Start the repo's own MCP server through the real client path."""
    server = {
        "name": "pythonw-selftest",
        # The child must be a console interpreter: the SDK gives it
        # stdin/stdout pipes, and `mcp.server` writes protocol frames
        # there. Only stderr is inherited, which is the bug under test.
        "command": str(Path(sys.executable).with_name("python.exe")),
        "args": ["-m", "mcp.server"],
        "cwd": str(ROOT),
    }
    handle = await runtime._start_server(server)
    tools = [t["name"] for t in (handle or {}).get("tools") or []]
    if handle:
        await runtime._close_quietly(handle.get("session_cm"),
                                     handle.get("transport_cm"))
    return tools


def main() -> int:
    out = Path(os.environ["JARVIS_PW_PROBE_OUT"])
    record = {
        "stdout_none": sys.stdout is None,
        "stderr_none": sys.stderr is None,
    }
    try:
        import asyncio

        from mcp import runtime

        handle = runtime._errlog()
        record["handle_name"] = str(getattr(handle, "name", ""))
        record["handle_fd"] = handle.fileno()
        handle.write("pythonw probe: errlog handle is live\n")
        handle.flush()
        record["served_exit"] = _run_grandchild(handle)
        record["unserved_exit"] = _run_grandchild(None)
        record["mcp_tools"] = asyncio.run(
            asyncio.wait_for(_mcp_roundtrip(runtime), timeout=90))
        record["ok"] = True
    except Exception as exc:  # noqa: BLE001 - the verdict must reach the test
        record["ok"] = False
        record["error"] = f"{type(exc).__name__}: {exc}"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record), encoding="utf-8")
    return 0 if record.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
