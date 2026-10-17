"""v1.25.0 — trace + flags, zero new features.

Principle 9 (traceable actions): every chat-loop tool call and every
consent verdict lands in one append-only audit trail, served newest-
first via GET /api/audit.  Principle 8 (staged rollout): the
sub-agent pool moves behind the `subagents_enabled` pref flag.  The
principle-8 demo flow (read -> edit -> verify -> report) runs here
end-to-end through the real tools as its log evidence.
"""
import contextlib
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


def _chunk(text=None, finish=None, tool_calls=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=text, reasoning_content=None,
                              tool_calls=tool_calls),
        finish_reason=finish)])


def _stream_of(*texts):
    for t in texts:
        yield _chunk(t)


def _tool_call_stream(name, args):
    yield _chunk(tool_calls=[SimpleNamespace(
        index=0, id="call_1",
        function=SimpleNamespace(name=name, arguments=args))])
    yield _chunk(finish="tool_calls")


class AuditFileTests(unittest.TestCase):
    def setUp(self):
        from system import audit as trail
        self.trail = trail
        self.tmp = Path(tempfile.mkdtemp()) / "audit.log"
        p = mock.patch.object(trail, "_FILE", self.tmp)
        p.start()
        self.addCleanup(p.stop)

    def test_record_format_and_tail_order(self):
        self.trail.record("tool", "fs_read", True, "{'path': 'a'}")
        self.trail.record("consent_deny", "term_run", True, "#4")
        lines = self.tmp.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 2)
        self.assertRegex(
            lines[0], r"\[\d{4}-.*\] OK\s+tool\s+fs_read")
        tail = self.trail.read_tail()
        self.assertEqual(len(tail), 2)
        self.assertIn("consent_deny", tail[0])   # newest first
        self.assertIn("fs_read", tail[1])

    def test_tail_limit_and_bad_input(self):
        for i in range(10):
            self.trail.record("tool", f"t{i}", True)
        self.assertEqual(len(self.trail.read_tail(3)), 3)
        self.assertEqual(len(self.trail.read_tail("abc")), 10)
        self.assertEqual(len(self.trail.read_tail(-5)), 1)

    def test_tail_capped_at_200(self):
        for i in range(205):
            self.trail.record("tool", f"t{i}", True)
        self.assertEqual(len(self.trail.read_tail(9999)), 200)

    def test_missing_file_reads_empty(self):
        self.assertEqual(self.trail.read_tail(), [])

    def test_record_never_raises(self):
        with mock.patch.object(self.trail, "_FILE", Path("/nope/x.log")):
            self.trail.record("tool", "x", True)   # parent unmakable
        with mock.patch("builtins.open", side_effect=RuntimeError("io")):
            self.trail.record("tool", "x", True)
            self.assertEqual(self.trail.read_tail(), [])

    def test_os_mission_audit_uses_shared_trail(self):
        from ai import os_mode
        os_mode._audit("propose", "term_run dir", True, "dry-run")
        lines = self.tmp.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("OK", lines[0])
        self.assertIn("propose", lines[0])


class LoopAuditTests(unittest.TestCase):
    def setUp(self):
        import ai.client as ac
        from ai import approvals as ap
        from system import audit as trail
        self.ac = ac
        ac._cooling.clear()
        ap._pending.clear()
        ap._next_id = 1
        self.addCleanup(ac._cooling.clear)
        self.addCleanup(ap._pending.clear)
        self.tmp = Path(tempfile.mkdtemp()) / "audit.log"
        p = mock.patch.object(trail, "_FILE", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(
            ac, "pick_model", return_value="primary-model"))
        stack.enter_context(mock.patch.object(
            ac, "resolve_client", return_value=object()))
        stack.enter_context(mock.patch.object(
            ac, "extra_provider_names", return_value=[]))
        stack.enter_context(mock.patch.object(
            ac, "FALLBACK_CHAIN", ["backup-model"]))
        stack.enter_context(mock.patch.object(
            ac, "current_mood",
            return_value=SimpleNamespace(temperature=0.7, max_tokens=100,
                                         use_reasoner=False,
                                         prefer_fastest=False)))
        stack.enter_context(mock.patch("memory.get_pref",
                                       return_value="ask"))
        self.addCleanup(stack.close)

    def _client(self, open_stream):
        c = self.ac.AIClient.__new__(self.ac.AIClient)
        c._client = object()
        c._system_prompt = lambda: "system prompt"
        c._last_user_text = lambda msgs: msgs[-1]["content"]
        c._open_stream = open_stream
        return c

    def _one_tool_run(self, name, args):
        calls = []

        def open_stream(model, messages, schemas, mood, client=None):
            calls.append(1)
            if len(calls) > 1:
                return _stream_of("done")
            return _tool_call_stream(name, args)

        # Real execute_tool: the audit must come from the choke
        # point itself, not from a mock.
        return list(self._client(open_stream).stream(
            [{"role": "user", "content": "hi"}],
            tools=[{"dummy": True}]))

    def test_executed_tool_leaves_ok_line(self):
        pieces = self._one_tool_run("outcome_stats", "{}")
        tr = next(p for k, p in pieces if k == "tool_result")
        self.assertIn("Outcomes:", tr["result"])
        lines = self.tmp.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("OK", lines[0])
        self.assertIn("outcome_stats", lines[0])

    def test_failed_tool_leaves_fail_line(self):
        self._one_tool_run("fs_read",
                           '{"path": "C:/Windows/System32/nope.txt"}')
        lines = self.tmp.read_text(encoding="utf-8").splitlines()
        self.assertIn("FAIL", lines[0])
        self.assertIn("fs_read", lines[0])

    def test_parked_consent_leaves_park_line(self):
        pieces = self._one_tool_run(
            "fs_write", '{"path": "a.txt", "content": "hi"}')
        tr = next(p for k, p in pieces if k == "tool_result")
        self.assertIn("[awaiting approval #1", tr["result"])
        lines = self.tmp.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 1)
        self.assertIn("consent_park", lines[0])
        self.assertIn("#1", lines[0])

    def test_consent_verdicts_audited(self):
        from ai import approvals as ap
        pid = ap.propose("fs_write", {"path": "a"})
        with mock.patch("ai.tools.execute_tool", return_value="ok"):
            ap.handle_approval_text(f"allow {pid}")
        pid2 = ap.propose("term_run", {"command": "x"})
        with mock.patch("ai.tools.execute_tool") as ex:
            ap.handle_approval_text(f"deny {pid2}")
        ex.assert_not_called()
        text = self.tmp.read_text(encoding="utf-8")
        self.assertIn("consent_run", text)
        self.assertIn("consent_deny", text)


class DemoFlowTests(unittest.TestCase):
    """Principle 8's single safe demo flow, end to end through the
    real tools: read -> edit -> verify -> report, with the audit
    trail as its evidence."""

    def setUp(self):
        from ai import tools_fs as tfs
        from system import audit as trail
        self.tfs = tfs
        self.root = Path(tempfile.mkdtemp())
        self.bak = self.root / "backups"
        self.bak.mkdir()
        self.logf = Path(tempfile.mkdtemp()) / "audit.log"
        patches = [
            mock.patch.object(tfs, "_ALLOWED_ROOTS", [self.root]),
            mock.patch.object(tfs, "_BACKUPS", self.bak),
            mock.patch.object(trail, "_FILE", self.logf),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_read_edit_verify_report(self):
        from ai.tools import execute_tool
        target = str(self.root / "demo.py")
        # write
        w = execute_tool("fs_write",
                         {"path": target, "content": "x = 1\n"})
        self.assertIn("[ok]", w)
        self.assertIn("verify: ok", w)
        # edit
        e = execute_tool("fs_replace",
                         {"path": target, "old": "x = 1", "new": "x = 2"})
        self.assertIn("[ok] replaced 1", e)
        self.assertIn("verify: ok", e)
        # read back (fs uses bytes mode: Windows newlines survive)
        r = execute_tool("fs_read", {"path": target})
        self.assertEqual(r.replace("\r\n", "\n"), "x = 2\n")
        # report: the trail proves each step ran and passed
        lines = self.logf.read_text(encoding="utf-8").splitlines()
        actions = [ln for ln in lines if " OK " in ln]
        self.assertGreaterEqual(len(actions), 3)
        self.assertTrue(any("fs_write" in ln for ln in actions))
        self.assertTrue(any("fs_replace" in ln for ln in actions))
        self.assertTrue(any("fs_read" in ln for ln in actions))


class AuditEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from server import app
        except Exception as exc:
            raise unittest.SkipTest(f"app import failed: {exc}")
        cls.app = app
        cls.app.testing = True
        cls.client = app.test_client()

    def setUp(self):
        from system import audit as trail
        self.tmp = Path(tempfile.mkdtemp()) / "audit.log"
        p = mock.patch.object(trail, "_FILE", self.tmp)
        p.start()
        self.addCleanup(p.stop)
        self.trail = trail

    def test_tail_endpoint_newest_first(self):
        self.trail.record("tool", "a", True)
        self.trail.record("consent_deny", "b", True)
        r = self.client.get("/api/audit")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(d["count"], 2)
        self.assertIn("consent_deny", d["entries"][0])
        self.assertIn("tool", d["entries"][1])

    def test_limit_param(self):
        for i in range(5):
            self.trail.record("tool", f"t{i}", True)
        d = self.client.get("/api/audit?limit=2").get_json()
        self.assertEqual(d["count"], 2)
        d = self.client.get("/api/audit?limit=abc").get_json()
        self.assertEqual(d["count"], 5)

    def test_empty_trail_is_empty_list(self):
        d = self.client.get("/api/audit").get_json()
        self.assertEqual(d, {"entries": [], "count": 0})


class SubagentsFlagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from server import app
        except Exception as exc:
            raise unittest.SkipTest(f"app import failed: {exc}")
        cls.app = app
        cls.app.testing = True
        cls.client = app.test_client()

    def setUp(self):
        self.saved = []
        store = SimpleNamespace(
            messages_for=lambda sid, text: [{"role": "user",
                                             "content": text}],
            record_reply=lambda sid, text: self.saved.append(text))
        patches = [
            mock.patch("routes.api.get_store", return_value=store),
            mock.patch("routes.api.dispatch_skill", return_value=None),
            mock.patch("skills.auto_generator.handle_approval_text",
                       return_value=None),
            mock.patch("skills.auto_generator.propose_if_enabled",
                       return_value=None),
            mock.patch("routes.api._speak_quiet", return_value=None),
            mock.patch("routes.api.extract_memory_async",
                       return_value=None),
            mock.patch("memory.outcomes.record", return_value=None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _post(self, text, agents_on, client):
        def pref(key, default=None):
            if key == "subagents_enabled":
                return agents_on
            return default
        with mock.patch("memory.get_pref", side_effect=pref), \
                mock.patch("routes.api.get_client", return_value=client):
            r = self.client.post("/api/command", json={"text": text})
            return r.get_data(as_text=True)

    def test_flag_off_skips_pool(self):
        from ai import agents as ag
        fake = SimpleNamespace(
            should_use_agents=lambda t: True,
            stream=lambda messages, tools=None: iter(
                [("content", "Direct.")]))
        with mock.patch.object(ag, "run") as run:
            body = self._post("compare the merits of tea versus coffee "
                              "for morning focus", False, fake)
        run.assert_not_called()
        self.assertNotIn("sub-agents", body)
        self.assertIn("Direct.", body)

    def test_flag_on_uses_pool(self):
        from ai import agents as ag
        fake = SimpleNamespace(
            should_use_agents=lambda t: True,
            stream=lambda messages, tools=None: iter([]))
        res = {"ok": True, "mode": "single", "answer": "Pooled.",
               "tasks": 1, "ok_tasks": 1}
        with mock.patch.object(ag, "run", return_value=res):
            body = self._post("compare the merits of tea versus coffee "
                              "for morning focus", True, fake)
        self.assertIn("Consulting sub-agents", body)
        self.assertIn("Pooled.", body)

    def test_flag_defaults_off_when_pref_missing(self):
        from memory import prefs as prefs_mod
        self.assertIn("subagents_enabled", prefs_mod._DEFAULTS)
        self.assertFalse(prefs_mod._DEFAULTS["subagents_enabled"])


if __name__ == "__main__":
    unittest.main()
