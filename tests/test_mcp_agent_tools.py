"""v1.23.0 — MCP tools safe to offer.

The wiring existed (route appends mcp_schemas(), execute_tool speaks
mcp__server__tool), but it had never been tested and three sharp
edges: one malformed server entry could kill the whole AI request,
a schema built while a 45s spawn held the runtime lock blocked the
user's reply, and catalog order followed server start order.  Now
the snapshot is bounded with a last-known-good fallback, bad entries
are skipped per-tool, and output is sorted.  None of it may raise.
"""
import unittest
from unittest import mock


def _entry(server="time", name="get_time", desc="clock",
           schema=None, full=None):
    return {"server": server, "name": name, "description": desc,
            "input_schema": ({"type": "object", "properties": {}}
                             if schema is None else schema),
            "full_name": full or f"mcp__{server}__{name}"}


class ToolsSnapshotTests(unittest.TestCase):
    def setUp(self):
        from mcp import runtime
        self.rt = runtime
        self.saved_servers = dict(runtime._servers)
        self.saved_cache = list(runtime._tools_cache)
        runtime._servers.clear()
        runtime._tools_cache.clear()
        self.addCleanup(self._restore)

    def _restore(self):
        self.rt._servers.clear()
        self.rt._servers.update(self.saved_servers)
        self.rt._tools_cache.clear()
        self.rt._tools_cache.extend(self.saved_cache)

    def test_fresh_snapshot_lists_running_tools(self):
        self.rt._servers["time"] = {
            "tools": [{"name": "get_time", "description": "clock",
                       "input_schema": {}}]}
        self.rt._servers["dead"] = None
        out = self.rt.tools_snapshot()
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["full_name"], "mcp__time__get_time")
        # success refreshes the fallback cache
        self.assertEqual(len(self.rt._tools_cache), 1)

    def test_busy_lock_serves_cache_instead_of_blocking(self):
        self.rt._tools_cache.append(_entry())
        self.rt._lock.acquire()
        try:
            out = self.rt.tools_snapshot(timeout=0.05)
        finally:
            self.rt._lock.release()
        self.assertEqual(out, [_entry()])

    def test_busy_lock_empty_cache_means_no_tools_not_a_hang(self):
        self.rt._lock.acquire()
        try:
            out = self.rt.tools_snapshot(timeout=0.05)
        finally:
            self.rt._lock.release()
        self.assertEqual(out, [])

    def test_snapshot_never_raises(self):
        with mock.patch.object(self.rt, "_servers", {"x": "not-a-dict"}):
            self.assertEqual(self.rt.tools_snapshot(), [])


class McpSchemasTests(unittest.TestCase):
    def _schemas(self, entries):
        from ai import tool_dispatch as td
        with mock.patch("mcp.runtime.tools_snapshot",
                        return_value=entries):
            return td.mcp_schemas()

    def test_good_entry_becomes_schema(self):
        out = self._schemas([_entry()])
        self.assertEqual(len(out), 1)
        fn = out[0]["function"]
        self.assertEqual(fn["name"], "mcp__time__get_time")
        self.assertTrue(fn["description"].startswith("[time]"))

    def test_output_sorted_by_name(self):
        out = self._schemas([_entry(server="zeta", name="z"),
                             _entry(server="alpha", name="a")])
        names = [s["function"]["name"] for s in out]
        self.assertEqual(names, sorted(names))

    def test_malformed_entries_skipped_not_fatal(self):
        out = self._schemas([
            _entry(),
            {"server": "bad"},                       # missing name
            {"server": "", "name": "x", "full_name": "mcp____x"},
            {"server": "s", "name": "", "full_name": "mcp__s__"},
            "not-a-dict",
            None,
            _entry(server="ok", name="fine"),
        ])
        names = [s["function"]["name"] for s in out]
        self.assertIn("mcp__time__get_time", names)
        self.assertIn("mcp__ok__fine", names)
        self.assertEqual(len(out), 2)

    def test_non_dict_input_schema_replaced(self):
        out = self._schemas([_entry(schema="garbage")])
        self.assertEqual(out[0]["function"]["parameters"],
                         {"type": "object", "properties": {}})

    def test_runtime_explosion_yields_no_tools(self):
        from ai import tool_dispatch as td
        with mock.patch("mcp.runtime.tools_snapshot",
                        side_effect=RuntimeError("boom")):
            self.assertEqual(td.mcp_schemas(), [])


class McpDispatchTests(unittest.TestCase):
    def test_mcp_call_routed_with_parsed_names(self):
        from ai.tools import execute_tool
        with mock.patch("mcp.runtime.call_tool",
                        return_value="12:00") as ct:
            out = execute_tool("mcp__time__get_time", {"tz": "UTC"})
        ct.assert_called_once_with("time", "get_time", {"tz": "UTC"})
        self.assertEqual(out, "12:00")

    def test_bad_mcp_name_rejected(self):
        from ai.tools import execute_tool
        self.assertEqual(execute_tool("mcp__oops", {}),
                         "Invalid MCP tool name.")

    def test_server_not_running_passes_through(self):
        from ai.tools import execute_tool
        msg = "MCP server 'ghost' is not running."
        with mock.patch("mcp.runtime.call_tool", return_value=msg):
            self.assertEqual(execute_tool("mcp__ghost__tool", {}), msg)

    def test_unknown_tool_still_unknown(self):
        from ai.tools import execute_tool
        self.assertEqual(execute_tool("nope_not_a_tool", {}),
                         "Unknown tool: nope_not_a_tool")


if __name__ == "__main__":
    unittest.main()
