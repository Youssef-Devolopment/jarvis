"""MCP client runtime: tool-call dispatch across loop states."""
from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock


def _handle(loop=None, text="tool says hi"):
    async def fake_call_tool(name, arguments=None):
        return SimpleNamespace(content=[SimpleNamespace(text=text)])

    return {"session": SimpleNamespace(call_tool=fake_call_tool),
            "tools": [], "loop": loop}


class CallToolTests(unittest.TestCase):
    def test_idle_loop_drives_directly(self):
        from mcp import runtime
        loop = asyncio.new_event_loop()
        try:
            with mock.patch.dict(runtime._servers,
                                 {"s": _handle(loop)}, clear=False):
                res = runtime.call_tool("s", "t", {})
            self.assertIn("tool says hi", res)
        finally:
            loop.close()
            runtime._servers.pop("s", None)

    def test_no_loop_uses_fallback(self):
        from mcp import runtime
        with mock.patch.dict(runtime._servers,
                             {"s": _handle(None)}, clear=False):
            try:
                res = runtime.call_tool("s", "t", {})
            finally:
                runtime._servers.pop("s", None)
        self.assertIn("tool says hi", res)

    def test_missing_server_message(self):
        from mcp import runtime
        res = runtime.call_tool("nope", "t", {})
        self.assertIn("not running", res)


class StopServerTests(unittest.TestCase):
    def test_stop_unknown_returns_false(self):
        from mcp import runtime
        self.assertFalse(runtime.stop_server("definitely-not-running"))

    def test_is_running_and_names(self):
        from mcp import runtime
        self.assertFalse(runtime.is_running("definitely-not-running"))
        self.assertIsInstance(runtime.running_names(), list)
        self.assertNotIn("definitely-not-running", runtime.running_names())

    def test_stop_drops_handle_without_loop(self):
        from mcp import runtime
        handle = {"loop": None}
        with mock.patch.object(runtime, "_servers", {"fake": handle}):
            self.assertTrue(runtime.is_running("fake"))
            self.assertTrue(runtime.stop_server("fake"))
            self.assertFalse(runtime.is_running("fake"))


if __name__ == "__main__":
    unittest.main()
