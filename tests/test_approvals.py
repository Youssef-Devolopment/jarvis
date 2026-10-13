"""v1.24.0 — tool consent (allow/confirm/deny).

Read-only tools run free; state-changing tools park for consent
unless the `tool_approval` pref is "auto".  The loop cannot pause
mid-request, so a gated call becomes a numbered pending request and
"allow N" / "deny N" on the next turn resolves it.  Nothing here may
break the loop when prefs/memory are unavailable (fail safe to ask).
"""
import contextlib
import unittest
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


class TierTests(unittest.TestCase):
    def test_mutations_need_approval(self):
        from ai import approvals as ap
        for t in ("fs_write", "fs_append", "fs_replace", "fs_delete",
                  "fs_mkdir", "term_run", "term_python", "win_click",
                  "win_type", "focus_app", "launch_app",
                  "bridge_transfer", "computer_run"):
            self.assertTrue(ap.needs_approval(t), t)

    def test_third_party_side_effects_need_approval(self):
        from ai import approvals as ap
        self.assertTrue(ap.needs_approval("mcp__fetch__fetch"))
        self.assertTrue(ap.needs_approval("mcp__anything__x"))

    def test_reads_run_free(self):
        from ai import approvals as ap
        for t in ("fs_read", "fs_list", "fs_search", "web_search",
                  "silent_browse", "remember_fact", "outcome_stats",
                  "read_screen", "open_url", "switch_mood",
                  "reality_check_tool"):
            self.assertFalse(ap.needs_approval(t), t)
        self.assertFalse(ap.needs_approval(""))
        self.assertFalse(ap.needs_approval(None))

    def test_mode_defaults_to_ask_and_fails_safe(self):
        from ai import approvals as ap
        with mock.patch("memory.get_pref", return_value="ask"):
            self.assertEqual(ap.approval_mode(), "ask")
        with mock.patch("memory.get_pref", return_value="auto"):
            self.assertEqual(ap.approval_mode(), "auto")
        with mock.patch("memory.get_pref", return_value="weird"):
            self.assertEqual(ap.approval_mode(), "ask")
        with mock.patch("memory.get_pref",
                        side_effect=RuntimeError("db down")):
            self.assertEqual(ap.approval_mode(), "ask")
            self.assertTrue(ap.gate_active())


class StoreTests(unittest.TestCase):
    def setUp(self):
        from ai import approvals as ap
        self.ap = ap
        ap._pending.clear()
        ap._next_id = 1
        self.addCleanup(ap._pending.clear)

    def test_propose_approve_roundtrip(self):
        pid = self.ap.propose("fs_write", {"path": "a.txt"})
        self.assertEqual(pid, 1)
        self.assertEqual(len(self.ap.pending_list()), 1)
        # approve pops it; a second approve finds nothing
        with mock.patch("ai.tools.execute_tool",
                        return_value="wrote it") as ex:
            out = self.ap.handle_approval_text(f"allow {pid}")
        ex.assert_called_once_with("fs_write", {"path": "a.txt"})
        self.assertEqual(out, "wrote it")
        self.assertIn("Nothing is waiting",
                      self.ap.handle_approval_text(f"allow {pid}"))

    def test_deny_never_executes(self):
        pid = self.ap.propose("term_run", {"command": "rm -rf /"})
        with mock.patch("ai.tools.execute_tool") as ex:
            out = self.ap.handle_approval_text(f"deny {pid}")
        ex.assert_not_called()
        self.assertIn("Denied", out)

    def test_unknown_id_lists_open_requests(self):
        pid = self.ap.propose("fs_delete", {"path": "x"})
        out = self.ap.handle_approval_text("allow 999")
        self.assertIn("Nothing is waiting under #999", out)
        self.assertIn(f"#{pid}", out)

    def test_unknown_id_with_empty_queue(self):
        out = self.ap.handle_approval_text("deny 7")
        self.assertIn("no open requests", out)

    def test_expired_requests_vanish(self):
        import time
        pid = self.ap.propose("fs_write", {"path": "a"})
        self.ap._pending[pid]["ts"] = time.time() - 9999
        self.assertEqual(self.ap.pending_list(), [])
        self.assertIn("no open requests",
                      self.ap.handle_approval_text(f"allow {pid}"))

    def test_queue_capped(self):
        for _ in range(25):
            self.ap.propose("fs_write", {"path": "a"})
        self.assertLessEqual(len(self.ap.pending_list()), 20)

    def test_long_result_trimmed_for_speech(self):
        pid = self.ap.propose("fs_read", {"path": "big"})
        with mock.patch("ai.tools.execute_tool",
                        return_value="z" * 5000):
            out = self.ap.handle_approval_text(f"approve {pid}")
        self.assertLessEqual(len(out), 1600)
        self.assertIn("trimmed", out)

    def test_execute_failure_reported_not_raised(self):
        pid = self.ap.propose("fs_write", {"path": "a"})
        with mock.patch("ai.tools.execute_tool",
                        side_effect=RuntimeError("disk full")):
            out = self.ap.handle_approval_text(f"allow {pid}")
        self.assertIn("failed", out)
        self.assertIn("disk full", out)


class MatcherTests(unittest.TestCase):
    def test_verdicts_match(self):
        from ai import approvals as ap
        self.assertEqual(ap.match_approval("allow 3"), ("allow", 3))
        self.assertEqual(ap.match_approval("deny 3"), ("deny", 3))
        self.assertEqual(ap.match_approval("Approve #12"), ("allow", 12))
        self.assertEqual(ap.match_approval("reject 2"), ("deny", 2))
        self.assertEqual(ap.match_approval("ALLOW 1."), ("allow", 1))

    def test_chat_is_not_a_verdict(self):
        from ai import approvals as ap
        for t in ("hello", "allow me to explain", "allow", "allow x",
                  "please allow 3", "allow 3 please", "", "yes", "no"):
            self.assertIsNone(ap.match_approval(t), t)

    def test_non_verdict_text_passes_through(self):
        from ai import approvals as ap
        self.assertIsNone(ap.handle_approval_text("what time is it"))


class StreamGateTests(unittest.TestCase):
    def setUp(self):
        import ai.client as ac
        from ai import approvals as ap
        self.ac = ac
        ac._cooling.clear()
        ap._pending.clear()
        ap._next_id = 1
        self.addCleanup(ac._cooling.clear)
        self.addCleanup(ap._pending.clear)
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
        self.addCleanup(stack.close)

    def _client(self, open_stream):
        c = self.ac.AIClient.__new__(self.ac.AIClient)
        c._client = object()
        c._system_prompt = lambda: "system prompt"
        c._last_user_text = lambda msgs: msgs[-1]["content"]
        c._open_stream = open_stream
        return c

    def _run(self, c, tool_events):
        with mock.patch("memory.get_pref", return_value="ask"):
            return list(c.stream([{"role": "user", "content": "hi"}],
                                 tools=[{"dummy": True}]))

    def test_gated_tool_parks_instead_of_running(self):
        from ai import approvals as ap
        calls = []

        def open_stream(model, messages, schemas, mood, client=None):
            calls.append(1)
            if len(calls) > 1:
                return _stream_of("I need your approval first.")
            return _tool_call_stream("fs_write",
                                     '{"path": "a.txt", "content": "hi"}')

        with mock.patch.object(self.ac, "execute_tool") as ex:
            pieces = self._run(self._client(open_stream), None)
        ex.assert_not_called()
        tr = next(p for k, p in pieces if k == "tool_result")
        self.assertIn("[awaiting approval #1", tr["result"])
        self.assertIn("Do NOT call it again", tr["result"])
        self.assertEqual(len(ap.pending_list()), 1)
        self.assertIn("approval",
                      [p for k, p in pieces if k == "content"][0])

    def test_read_tool_runs_free_in_ask_mode(self):
        calls = []

        def open_stream(model, messages, schemas, mood, client=None):
            calls.append(1)
            if len(calls) > 1:
                return _stream_of("done")
            return _tool_call_stream("fs_read", '{"path": "a.txt"}')

        with mock.patch.object(self.ac, "execute_tool",
                               return_value="file bytes") as ex:
            list(self._run(self._client(open_stream), None))
        ex.assert_called_once_with("fs_read", {"path": "a.txt"})

    def test_auto_mode_runs_everything(self):
        from ai import approvals as ap
        calls = []

        def open_stream(model, messages, schemas, mood, client=None):
            calls.append(1)
            if len(calls) > 1:
                return _stream_of("done")
            return _tool_call_stream("fs_write",
                                     '{"path": "a.txt", "content": "hi"}')

        c = self._client(open_stream)
        with mock.patch("memory.get_pref", return_value="auto"), \
                mock.patch.object(self.ac, "execute_tool",
                                  return_value="wrote") as ex:
            list(c.stream([{"role": "user", "content": "hi"}],
                          tools=[{"dummy": True}]))
        ex.assert_called_once()
        self.assertEqual(ap.pending_list(), [])


if __name__ == "__main__":
    unittest.main()
