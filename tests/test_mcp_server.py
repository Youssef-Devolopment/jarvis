"""End-to-end test of the native MCP stdio server (JSON-RPC handshake)."""
from __future__ import annotations
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class McpServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc = subprocess.Popen(
            [sys.executable, "-m", "mcp.server"],
            cwd=str(ROOT), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
            bufsize=1)
        cls._id = 0

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            try:
                cls.proc.wait(timeout=5)
            except Exception:
                cls.proc.kill()

    def _send(self, msg: dict) -> dict | None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read() or "(no stderr)"
            self.fail(f"server closed stdout. stderr: {err[:800]}")
        return json.loads(line)

    def _request(self, method: str, params: dict | None = None) -> dict:
        type(self)._id += 1
        msg = {"jsonrpc": "2.0", "id": type(self)._id, "method": method}
        if params is not None:
            msg["params"] = params
        reply = self._send(msg)
        self.assertIsNotNone(reply, f"no reply for {method}")
        return reply

    def test_01_initialize(self):
        r = self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "0"}})
        self.assertEqual(r["result"]["serverInfo"]["name"], "jarvis")
        self.assertIn("tools", r["result"]["capabilities"])
        # initialized notification must produce NO reply
        self.proc.stdin.write(json.dumps({
            "jsonrpc": "2.0",
            "method": "notifications/initialized"}) + "\n")
        self.proc.stdin.flush()

    def test_02_ping(self):
        r = self._request("ping")
        self.assertEqual(r["result"], {})

    def test_03_tools_list(self):
        r = self._request("tools/list")
        names = [t["name"] for t in r["result"]["tools"]]
        for expected in ("jarvis_skills", "jarvis_command", "jarvis_terminal",
                         "jarvis_memory", "jarvis_obsidian", "jarvis_ports",
                         "jarvis_screen_ocr"):
            self.assertIn(expected, names)
        for t in r["result"]["tools"]:
            self.assertIn("inputSchema", t)
            self.assertIn("description", t)

    def test_04_call_skills_tool(self):
        r = self._request("tools/call", {
            "name": "jarvis_skills", "arguments": {}})
        self.assertFalse(r["result"]["isError"])
        text = r["result"]["content"][0]["text"]
        self.assertGreater(len(text), 100)   # 100+ skills listed

    def test_05_call_memory_tool(self):
        r = self._request("tools/call", {
            "name": "jarvis_memory",
            "arguments": {"action": "add",
                          "fact": "mcp-server-test fact 42"}})
        self.assertFalse(r["result"]["isError"])
        r2 = self._request("tools/call", {
            "name": "jarvis_memory",
            "arguments": {"action": "search", "query": "mcp-server-test"}})
        self.assertIn("mcp-server-test",
                      r2["result"]["content"][0]["text"])
        # clean up
        self._request("tools/call", {
            "name": "jarvis_memory",
            "arguments": {"action": "forget", "query": "mcp-server-test"}})

    def test_06_bad_tool_is_typed_error(self):
        r = self._request("tools/call", {
            "name": "nope", "arguments": {}})
        self.assertTrue(r["result"]["isError"])

    def test_07_unknown_method(self):
        r = self._request("bogus/method")
        self.assertEqual(r["error"]["code"], -32601)

    def test_08_resources_list_and_read(self):
        r = self._request("resources/list")
        uris = [x["uri"] for x in r["result"]["resources"]]
        self.assertIn("jarvis://skills", uris)
        self.assertIn("jarvis://memory/facts", uris)
        r2 = self._request("resources/read",
                           {"uri": "jarvis://skills"})
        self.assertIn("text", r2["result"]["contents"][0])
        r3 = self._request("resources/read", {"uri": "jarvis://nope"})
        self.assertIn("error", r3)


if __name__ == "__main__":
    unittest.main()
