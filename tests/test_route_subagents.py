"""v1.24.0 — sub-agent fan-out and consent verdicts at the route.

A multi-part question that misses every skill fans out to the
parallel pool (plan -> run -> merge) with visible status events; a
failed pool degrades to the normal single loop, never an error.  An
"allow N" / "deny N" turn resolves a parked consent request and its
result comes back as the reply.  The Flask app is real; the client,
store, skills, drafter, speaker and memory side-channels are faked.
"""
import unittest
from types import SimpleNamespace
from unittest import mock


def _sse_text(resp):
    return resp.get_data(as_text=True)


def _store_fake(saved):
    return SimpleNamespace(
        messages_for=lambda sid, text: [{"role": "user",
                                         "content": text}],
        record_reply=lambda sid, text: saved.append((sid, text)))


class RouteSubagentsTests(unittest.TestCase):
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
        patches = [
            mock.patch("routes.api.get_store",
                       return_value=_store_fake(self.saved)),
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

    def _fake_client(self, want_agents, stream_events):
        return SimpleNamespace(
            should_use_agents=lambda text: want_agents,
            stream=lambda messages, tools=None: iter(stream_events))

    def _post(self, text, client):
        # Consume INSIDE the caller's mock context: the SSE generate()
        # below is lazy, and patches must still be active when it runs.
        with mock.patch("routes.api.get_client", return_value=client):
            r = self.client.post("/api/command", json={"text": text})
            body = r.get_data(as_text=True)
        return r, body

    def test_parallel_answer_streams_with_status(self):
        from ai import agents as ag
        res = {"ok": True, "mode": "parallel", "answer": "Merged verdict.",
               "tasks": 3, "ok_tasks": 2, "elapsed": 1.0}
        with mock.patch.object(ag, "run", return_value=res):
            r, body = self._post("compare the merits of tea versus coffee "
                                 "for morning focus",
                                 self._fake_client(True, []))
        self.assertEqual(r.status_code, 200)
        self.assertIn("Consulting sub-agents", body)
        self.assertIn("2/3 sub-tasks answered", body)
        self.assertIn("Merged verdict.", body)
        self.assertIn('"source": "llm"', body)
        self.assertIn("[DONE]", body)
        self.assertEqual(self.saved[-1][1], "Merged verdict.")

    def test_failed_pool_falls_through_to_single_loop(self):
        from ai import agents as ag
        events = [("content", "Direct answer.")]
        with mock.patch.object(ag, "run",
                               return_value={"ok": False, "answer": "",
                                             "mode": "error"}):
            r, body = self._post("compare the merits of tea versus coffee "
                                 "for morning focus",
                                 self._fake_client(True, events))
        self.assertIn("came up empty", body)
        self.assertIn("Direct answer.", body)
        self.assertEqual(self.saved[-1][1], "Direct answer.")

    def test_pool_exception_falls_through(self):
        from ai import agents as ag
        events = [("content", "Direct answer.")]
        with mock.patch.object(ag, "run",
                               side_effect=RuntimeError("boom")):
            r, body = self._post("compare the merits of tea versus coffee "
                                 "for morning focus",
                                 self._fake_client(True, events))
        self.assertIn("Direct answer.", body)

    def test_simple_question_skips_pool(self):
        from ai import agents as ag
        events = [("content", "Justhi.")]
        with mock.patch.object(ag, "run") as run:
            r, body = self._post("what time is it",
                                 self._fake_client(False, events))
        run.assert_not_called()
        self.assertNotIn("sub-agents", body)
        self.assertIn("Justhi.", body)


class RouteConsentTests(unittest.TestCase):
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
        from ai import approvals as ap
        ap._pending.clear()
        ap._next_id = 1
        self.addCleanup(ap._pending.clear)
        self.saved = []
        patches = [
            mock.patch("routes.api.get_store",
                       return_value=_store_fake(self.saved)),
            mock.patch("routes.api.dispatch_skill", return_value=None),
            mock.patch("skills.auto_generator.handle_approval_text",
                       return_value=None),
            mock.patch("skills.auto_generator.propose_if_enabled",
                       return_value=None),
            mock.patch("routes.api._speak_quiet", return_value=None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _post(self, text):
        return self.client.post("/api/command", json={"text": text})

    def test_allow_runs_parked_tool_and_replies(self):
        from ai import approvals as ap
        pid = ap.propose("fs_write", {"path": "a.txt",
                                      "content": "hi"})
        with mock.patch("ai.tools.execute_tool",
                        return_value="wrote 2 chars") as ex:
            r = self._post(f"allow {pid}")
        ex.assert_called_once_with("fs_write", {"path": "a.txt",
                                                "content": "hi"})
        body = _sse_text(r)
        self.assertIn("wrote 2 chars", body)
        self.assertIn('"source": "consent"', body)
        self.assertEqual(self.saved[-1][1], "wrote 2 chars")

    def test_deny_refuses_without_running(self):
        from ai import approvals as ap
        pid = ap.propose("term_run", {"command": "format C:"})
        with mock.patch("ai.tools.execute_tool") as ex:
            r = self._post(f"deny {pid}")
        ex.assert_not_called()
        self.assertIn("Denied", _sse_text(r))

    def test_unknown_number_is_honest(self):
        r = self._post("allow 4242")
        self.assertIn("Nothing is waiting", _sse_text(r))


if __name__ == "__main__":
    unittest.main()
