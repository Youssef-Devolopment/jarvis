"""Prove the MCP stderr fix under a REAL pythonw.exe launch.

The unit tests in test_mcp_runtime.py patch `sys.stderr` to None, which
proves the branch but not the condition. Everything the app does at
runtime starts from `pythonw.exe`: no console, no stdout, no stderr. A
retry layer shipped in 1.33.4 because that gap was never exercised, and
it was reverted a day later (DECISIONS #14).

This test starts the real `pythonw.exe` that sits beside the running
interpreter and runs tests/pythonw_probe.py inside it. The probe checks
the windowless state is genuine, takes the handle `mcp.runtime._errlog()`
returns, and starts a child that writes a startup banner - the exact
thing that used to kill MCP servers. It also starts that child with
`stderr=None` and requires it to fail, so the test cannot pass on a
machine that has quietly stopped reproducing the bug.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROBE = ROOT / "tests" / "pythonw_probe.py"
PYTHONW = Path(sys.executable).with_name("pythonw.exe")


@unittest.skipUnless(sys.platform == "win32" and PYTHONW.is_file(),
                     "pythonw.exe is a Windows interpreter")
class PythonwSmokeTests(unittest.TestCase):
    """One probe launch, four assertions."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name) / "probe.json"
        env = dict(os.environ)
        env["JARVIS_PW_PROBE_OUT"] = str(out)
        env["PYTHONIOENCODING"] = "utf-8"
        # DETACHED_PROCESS with no inherited handles is the closest a CI
        # runner gets to a Start-menu launch: no console, no stdout, no
        # stderr. Passing PIPE or DEVNULL here would hand the child valid
        # handles and the probe would be testing a different program.
        cls.proc = subprocess.run(
            [str(PYTHONW), str(PROBE)],
            cwd=str(ROOT),
            env=env,
            creationflags=subprocess.DETACHED_PROCESS,
            timeout=120,
        )
        cls.record = (json.loads(out.read_text(encoding="utf-8"))
                      if out.is_file() else {})

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_probe_runs_to_completion(self):
        self.assertEqual(
            self.proc.returncode, 0,
            f"probe failed (exit {self.proc.returncode}): {self.record}")
        self.assertTrue(self.record.get("ok"), self.record)

    def test_the_windowless_state_is_real(self):
        # If pythonw ever grew a console, the rest of this test would be
        # meaningless, so assert the precondition instead of assuming it.
        self.assertTrue(self.record.get("stdout_none"))
        self.assertTrue(self.record.get("stderr_none"))

    def test_errlog_is_a_live_handle_without_a_console(self):
        self.assertIn("mcp_stderr.log", self.record.get("handle_name", ""))
        self.assertGreaterEqual(self.record.get("handle_fd", -1), 0)

    def test_a_logging_child_survives_and_the_unserved_one_fails(self):
        self.assertEqual(
            self.record.get("served_exit"), 0,
            "a child given _errlog() must be able to write its banner")
        self.assertNotEqual(
            self.record.get("unserved_exit"), 0,
            "stderr=None no longer kills the child - the guard is stale")

    def test_a_real_mcp_server_completes_the_handshake(self):
        tools = self.record.get("mcp_tools") or []
        self.assertTrue(tools, "the MCP server listed no tools")
        self.assertIn("jarvis_skills", tools)


if __name__ == "__main__":
    unittest.main()
