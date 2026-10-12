"""Agent-loop hardening (1.21.0): the loop existed, this covers its
weaknesses.

1. Dead-model tax — a provider saying "gone" (campaign ended, 404)
   used to be retried on EVERY request forever.  Now the model cools
   down for 10 minutes and rejoins rotation when the entry expires.
2. Unbounded tool results — a runaway MCP/terminal result could blow
   a small free-model context mid-loop; the model-bound copy is now
   capped (the display event was already capped at 300 chars).
3. Budget exhaustion — if every round asked for another tool, the
   loop fell off the end with NO answer.  Now one final no-tools
   pass guarantees the user hears a reply.
4. Step visibility — tool_call events carry step/steps so consumers
   can show how deep into the budget the model is.
"""
import contextlib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


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


class AgentLoopTests(unittest.TestCase):
    def setUp(self):
        import ai.client as ac
        self.ac = ac
        ac._cooling.clear()
        self.addCleanup(ac._cooling.clear)
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
        c = self.ac.AIClient.__new__(self.ac.AIClient)   # skip key init
        c._client = object()
        c._system_prompt = lambda: "system prompt"
        c._last_user_text = lambda msgs: msgs[-1]["content"]
        c._open_stream = open_stream
        return c

    @staticmethod
    def _msgs():
        return [{"role": "user", "content": "hi"}]

    def test_failed_model_cools_and_is_skipped_next_request(self):
        attempts = []

        def open_stream(model, *a, **k):
            attempts.append(model)
            if model == "primary-model":
                raise RuntimeError("model does not exist")
            return _stream_of("Hello there")

        c = self._client(open_stream)
        list(c.stream(self._msgs()))
        self.assertEqual(attempts, ["primary-model", "backup-model"])
        self.assertIn("primary-model", self.ac._cooling)

        attempts.clear()
        list(c.stream(self._msgs()))
        # the cooled model is never attempted again until expiry
        self.assertEqual(attempts, ["backup-model"])

    def test_cooldown_expires_and_model_rejoins_rotation(self):
        self.ac._cool_down("gone-model", ttl=0.0)
        self.assertNotIn("gone-model", self.ac._cooling_snapshot())
        self.ac._cool_down("gone-model", ttl=999.0)
        self.assertIn("gone-model", self.ac._cooling_snapshot())

    def test_tool_result_capped_for_model_context(self):
        seen = []
        big = "x" * 20000

        def open_stream(model, messages, schemas, mood, client=None):
            seen.append(list(messages))
            if len(seen) == 1:
                return _tool_call_stream("fs_read", '{"path": "big.txt"}')
            return _stream_of("All done")

        with mock.patch.object(self.ac, "execute_tool", return_value=big):
            pieces = list(self._client(open_stream).stream(
                self._msgs(), tools=[{"dummy": True}]))

        tool_msgs = [m for m in seen[-1] if m.get("role") == "tool"]
        self.assertEqual(len(tool_msgs), 1)
        self.assertLessEqual(len(tool_msgs[0]["content"]), 6100)
        self.assertIn("[truncated", tool_msgs[0]["content"])
        # display event keeps its own 300-char cap
        tr = next(p for k, p in pieces if k == "tool_result")
        self.assertLessEqual(len(tr["result"]), 300)
        self.assertIn("All done", [p for k, p in pieces if k == "content"])

    def test_tool_event_carries_step_progress(self):
        calls = []

        def open_stream(model, messages, schemas, mood, client=None):
            calls.append(schemas)
            if len(calls) == 1:
                return _tool_call_stream("web_search", '{"q": "weather"}')
            return _stream_of("sunny")

        with mock.patch.object(self.ac, "execute_tool",
                               return_value="sunny 20C"):
            pieces = list(self._client(open_stream).stream(
                self._msgs(), tools=[{"dummy": True}], max_rounds=3))

        tc = next(p for k, p in pieces if k == "tool_call")
        self.assertEqual(tc["step"], 1)
        self.assertEqual(tc["steps"], 3)
        self.assertEqual(tc["name"], "web_search")
        tr = next(p for k, p in pieces if k == "tool_result")
        self.assertEqual(tr["result"], "sunny 20C")

    def test_budget_exhaustion_still_answers(self):
        opens = []

        def open_stream(model, messages, schemas, mood, client=None):
            opens.append(schemas)
            if schemas is None:              # the final no-tools pass
                return _stream_of("Final answer")
            return _tool_call_stream("web_search", '{"q": "x"}')

        with mock.patch.object(self.ac, "execute_tool", return_value="ok"):
            pieces = list(self._client(open_stream).stream(
                self._msgs(), tools=[{"dummy": True}], max_rounds=2))

        kinds = [k for k, _ in pieces]
        self.assertIn("status", kinds)
        status = next(p for k, p in pieces if k == "status")
        self.assertIn("budget", status)
        self.assertEqual([p for k, p in pieces if k == "content"],
                         ["Final answer"])
        # two tool rounds, then exactly one pass with tools withdrawn
        self.assertEqual(len(opens), 3)
        self.assertIsNone(opens[-1])

    def test_budget_exhaustion_never_silent(self):
        def open_stream(model, messages, schemas, mood, client=None):
            return _tool_call_stream("web_search", '{"q": "x"}')

        with mock.patch.object(self.ac, "execute_tool", return_value="ok"):
            pieces = list(self._client(open_stream).stream(
                self._msgs(), tools=[{"dummy": True}], max_rounds=1))

        content = [p for k, p in pieces if k == "content"]
        self.assertTrue(content, "budget exhaustion must still reply")
        self.assertIn("tool-step budget", content[0])


class FallbackChainHygieneTests(unittest.TestCase):
    def test_dead_model_out_of_default_chain(self):
        import ai.client as ac
        # campaign ended — this model 404s and must not sit in the
        # default rotation (cooldown covers it if picked as primary)
        self.assertNotIn("qwen3.8-flash:free", ac.FALLBACK_CHAIN)
        self.assertTrue(ac.FALLBACK_CHAIN)


if __name__ == "__main__":
    unittest.main()
