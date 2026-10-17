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


class SdkPathTests(unittest.TestCase):
    """Regression: _sdk() used to REMOVE the project root from the
    global sys.path while importing the SDK, which raced every other
    thread's imports (desktop boot vs Flask's first import died with
    "No module named 'routes'"). The window must be loss-free."""

    def test_sdk_window_removes_nothing_and_pins_sdk_first(self):
        import sys

        from mcp import runtime
        before = list(sys.path)
        with runtime._sdk_path() as sdk_base:
            during = list(sys.path)
        self.assertEqual(set(during), set(before))     # nothing removed
        self.assertEqual(during[0], sdk_base)          # SDK wins import
        self.assertEqual(sys.path, before)             # fully restored

    def test_sdk_import_still_returns_the_real_sdk(self):
        from mcp import runtime
        ClientSession, Params, stdio_client, TextContent = runtime._sdk()
        self.assertTrue(callable(ClientSession))
        self.assertTrue(callable(stdio_client))
        # the SDK's own types, not our local package's
        self.assertTrue(hasattr(TextContent, "model_fields")
                        or hasattr(TextContent, "__fields__"))


class FailedStartCleanupTests(unittest.IsolatedAsyncioTestCase):
    """A failed handshake must tear down the context managers it
    opened, or the child process leaks."""

    async def test_failed_handshake_closes_both_contexts(self):
        from mcp import runtime

        closed = []

        class FakeTransport:
            async def __aenter__(self):
                return ("read", "write")

            async def __aexit__(self, *exc):
                closed.append("transport")

        class FakeSessionCM:
            def __init__(self, read, write):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                closed.append("session")

            async def initialize(self):
                raise RuntimeError("handshake boom")

        def fake_stdio(params):
            return FakeTransport()

        def fake_params(**kw):
            return SimpleNamespace(**kw)

        with mock.patch.object(runtime, "_sdk",
                               return_value=(FakeSessionCM, fake_params,
                                             fake_stdio, object())):
            handle = await runtime._start_server(
                {"name": "x", "command": "probe", "args": []})

        self.assertIsNone(handle)
        self.assertIn("session", closed)
        self.assertIn("transport", closed)

    async def test_close_quietly_swallows_broken_exit(self):
        from mcp import runtime

        class Boom:
            async def __aexit__(self, *exc):
                raise RuntimeError("nope")

        # Teardown failing must not raise out of the helper.
        await runtime._close_quietly(Boom(), None)


class StartServerRetryTests(unittest.TestCase):
    def setUp(self):
        from mcp import runtime
        self.rt = runtime
        self._saved = dict(runtime._servers)
        runtime._servers.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        self.rt._servers.clear()
        self.rt._servers.update(self._saved)

    def _handle(self):
        return {"tools": [], "session": None, "session_cm": None,
                "transport_cm": None, "loop": None}

    def test_retries_once_then_succeeds(self):
        rt = self.rt
        srv = {"name": "s", "command": "c", "enabled": True}
        calls = []

        def fake_start(_srv):
            calls.append(1)
            return self._handle() if len(calls) == 2 else None

        with mock.patch.object(rt, "all_servers", return_value=[srv]), \
                mock.patch.object(rt, "_start_in_loop",
                                  side_effect=fake_start):
            self.assertTrue(rt.start_server("s"))
        self.assertEqual(len(calls), 2)
        self.assertTrue(rt.is_running("s"))

    def test_gives_up_after_attempts(self):
        rt = self.rt
        srv = {"name": "s", "command": "c", "enabled": True}
        with mock.patch.object(rt, "all_servers", return_value=[srv]), \
                mock.patch.object(rt, "_start_in_loop", return_value=None):
            self.assertFalse(rt.start_server("s", attempts=2))
        self.assertFalse(rt.is_running("s"))

    def test_already_running_short_circuits(self):
        rt = self.rt
        with mock.patch.object(rt, "_start_in_loop") as start:
            rt._servers["s"] = self._handle()
            self.assertTrue(rt.start_server("s"))
            start.assert_not_called()


class AbandonedStartTests(unittest.TestCase):
    """A start slower than the join budget must close its own handle
    instead of leaking a running child process."""

    def test_slow_start_is_abandoned_and_closed(self):
        import time as _time

        from mcp import runtime

        closed = []

        class CM:
            def __init__(self, tag):
                self.tag = tag

            async def __aexit__(self, *exc):
                closed.append(self.tag)

        async def slow(_srv):
            _time.sleep(0.5)
            return {"tools": [], "session": None,
                    "session_cm": CM("session"),
                    "transport_cm": CM("transport"),
                    "loop": asyncio.get_event_loop()}

        with mock.patch.object(runtime, "_start_server", side_effect=slow):
            handle = runtime._start_in_loop({"name": "x"}, timeout=0.1)

        self.assertIsNone(handle)
        _time.sleep(1.5)                     # thread acknowledges + closes
        self.assertIn("session", closed)
        self.assertIn("transport", closed)
        self.assertNotIn("x", runtime._servers)


if __name__ == "__main__":
    unittest.main()
