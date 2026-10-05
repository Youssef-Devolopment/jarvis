"""Agent loop: default-model routing (no hardcoded IDs), split /
single / merge paths, failure honesty — all LLM calls faked."""
from __future__ import annotations

import unittest
from unittest import mock

from ai import agents


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]


class FakeCompletions:
    """Routes by prompt shape: split -> JSON, merge -> final, else answer."""

    def __init__(self, calls, fail_tasks=False):
        self.calls = calls
        self.fail_tasks = fail_tasks

    def create(self, **kw):
        self.calls.append(kw)
        system = kw.get("messages", [{}])[0].get("content", "")
        user = " ".join(m.get("content", "")
                        for m in kw.get("messages", []))
        if "INDEPENDENT sub-tasks" in system:
            return _Resp('["task one", "task two"]')
        if "Sub-agent answers" in user:
            return _Resp("Combined final answer.")
        if self.fail_tasks:
            raise RuntimeError("provider down")
        return _Resp("Short answer.")


class FakeInner:
    def __init__(self, calls, fail_tasks=False):
        self.chat = mock.MagicMock()
        self.chat.completions = FakeCompletions(calls, fail_tasks)


class FakeClient:
    def __init__(self, calls, fail_tasks=False):
        self.default_model = "test-model"
        self._client = FakeInner(calls, fail_tasks)


def _patched(calls, fail_tasks=False):
    return mock.patch("ai.client.get_client",
                      return_value=FakeClient(calls, fail_tasks))


class AgentLoopTests(unittest.TestCase):
    def test_parallel_uses_default_model(self):
        calls = []
        with _patched(calls):
            res = agents.run("compare apples and oranges in detail")
        self.assertTrue(res["ok"])
        self.assertEqual(res["mode"], "parallel")
        self.assertEqual(res["tasks"], 2)
        self.assertEqual(res["answer"], "Combined final answer.")
        models = {c.get("model") for c in calls}
        self.assertEqual(models, {"test-model"})

    def test_single_when_split_says_single(self):
        calls = []

        class SingleSplit(FakeCompletions):
            def create(self, **kw):
                self.calls.append(kw)
                user = " ".join(m.get("content", "")
                                for m in kw.get("messages", []))
                if "INDEPENDENT sub-tasks" in kw["messages"][0]["content"]:
                    return _Resp("SINGLE")
                return _Resp("Only answer.")

        class SingleClient(FakeClient):
            def __init__(self):
                super().__init__(calls)
                inner = mock.MagicMock()
                inner.chat.completions = SingleSplit(calls)
                self._client = inner

        with mock.patch("ai.client.get_client",
                        return_value=SingleClient()):
            res = agents.run("a much longer question about fruit ripeness here")
        self.assertEqual(res["mode"], "single")
        self.assertEqual(res["answer"], "Only answer.")

    def test_all_tasks_failing_is_honest(self):
        calls = []
        with _patched(calls, fail_tasks=True):
            res = agents.run("compare apples and oranges in detail")
        # split still works (only tasks fail) -> merge has nothing
        self.assertFalse(res["ok"])
        self.assertIn("failed", res["answer"].lower())

    def test_should_use_agents_gate(self):
        self.assertFalse(agents.should_use_agents("hi"))
        self.assertFalse(agents.should_use_agents("what time is it"))
        self.assertTrue(agents.should_use_agents(
            "compare the pros and cons of both options in detail"))


class ModelErrorTests(unittest.TestCase):
    def test_expired_offer_counts_as_model_error(self):
        from ai.client import _is_model_error
        self.assertTrue(_is_model_error(Exception(
            'Error code: 404 - {"error": {"message": '
            '\'The free offer "Qwen3.8 Flash" has ended.\'}}')))
        self.assertTrue(_is_model_error(Exception("model not found")))
        self.assertTrue(_is_model_error(Exception("decommissioned model")))

    def test_real_errors_are_not_model_errors(self):
        from ai.client import _is_model_error
        self.assertFalse(_is_model_error(Exception("rate limit exceeded")))
        self.assertFalse(_is_model_error(Exception("connection reset")))
        self.assertFalse(_is_model_error(Exception("timeout")))

    def test_temp_rejection_retries_without_it(self):
        from ai.client import create_with_temp_fallback
        calls = []

        def fake_create(model=None, messages=None, temperature=None,
                        **kw):
            calls.append((model, temperature, kw))
            if temperature is not None:
                raise RuntimeError(
                    "Error code: 400 - temperature not accepted")
            return "STREAM-OK"

        out = create_with_temp_fallback(
            fake_create, "m", [{"role": "user", "content": "hi"}],
            0.2, max_tokens=10)
        self.assertEqual(out, "STREAM-OK")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][1], 0.2)
        self.assertIsNone(calls[1][1])
        self.assertEqual(calls[1][2].get("max_tokens"), 10)

    def test_other_errors_propagate(self):
        from ai.client import create_with_temp_fallback

        def fake_create(model=None, messages=None, temperature=None,
                        **kw):
            raise RuntimeError("Error code: 401 - invalid_api_key")

        with self.assertRaises(RuntimeError):
            create_with_temp_fallback(fake_create, "m", [], 0.2)

    def test_no_retry_when_temperature_none(self):
        from ai.client import create_with_temp_fallback
        calls = []

        def fake_create(model=None, messages=None, temperature=None,
                        **kw):
            calls.append(temperature)
            raise RuntimeError("Error code: 400 - temperature bad")

        with self.assertRaises(RuntimeError):
            create_with_temp_fallback(fake_create, "m", [], None)
        self.assertEqual(calls, [None])


class RetryAndSafetyTests(unittest.TestCase):
    def test_transient_failure_retries_then_succeeds(self):
        calls, n = [], {"n": 0}

        def flaky(*a, **kw):
            n["n"] += 1
            if n["n"] == 1:
                raise RuntimeError("blip")
            return _Resp("Recovered.")

        with mock.patch("ai.client.get_client",
                        return_value=FakeClient(calls)), \
             mock.patch("ai.client.create_with_temp_fallback",
                        side_effect=flaky), \
             mock.patch.object(agents.time, "sleep"):
            r = agents._run_one("do a thing")
        self.assertTrue(r["ok"])
        self.assertEqual(r["attempts"], 2)
        self.assertEqual(r["answer"], "Recovered.")

    def test_permanent_failure_returns_ok_false(self):
        calls = []
        with mock.patch("ai.client.get_client",
                        return_value=FakeClient(calls)), \
             mock.patch("ai.client.create_with_temp_fallback",
                        side_effect=RuntimeError("provider down")), \
             mock.patch.object(agents.time, "sleep"):
            r = agents._run_one("do a thing")
        self.assertFalse(r["ok"])
        self.assertIn("provider down", r["error"])

    def test_empty_answer_retried_once(self):
        calls, n = [], {"n": 0}

        def empty_then_answer(*a, **kw):
            n["n"] += 1
            return _Resp("" if n["n"] == 1 else "Second try works.")

        with mock.patch("ai.client.get_client",
                        return_value=FakeClient(calls)), \
             mock.patch("ai.client.create_with_temp_fallback",
                        side_effect=empty_then_answer), \
             mock.patch.object(agents.time, "sleep"):
            r = agents._run_one("do a thing")
        self.assertTrue(r["ok"])
        self.assertEqual(r["answer"], "Second try works.")

    def test_run_never_raises(self):
        with mock.patch.object(agents, "_plan_split",
                               side_effect=RuntimeError("boom")):
            res = agents.run("compare apples and oranges in detail")
        self.assertFalse(res["ok"])
        self.assertEqual(res["mode"], "error")
        self.assertIn("boom", res["answer"])

    def test_merge_notes_failed_subtasks(self):
        calls = []
        results = [{"ok": True, "task": "t1", "answer": "a1"},
                   {"ok": False, "task": "t2", "error": "e"}]
        with mock.patch("ai.client.get_client",
                        return_value=FakeClient(calls)):
            out = agents._merge("compare things", results)
        self.assertEqual(out, "Combined final answer.")
        merge_call = calls[-1]
        user = " ".join(m["content"] for m in merge_call["messages"])
        self.assertIn("1 of 2 sub-tasks FAILED", user)


if __name__ == "__main__":
    unittest.main()
