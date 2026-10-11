"""Fallback notices are status events, never reply text.

1.19.x shipped the fallback banner as a content piece
("[fallback to Mimo ●] "), which polluted the reply body, got stored
in conversation history, and the model then echoed it back verbatim —
one old marker bred whole rows of copies in later replies. 1.20.0
turns it into a status event that no consumer renders as text.
"""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def _chunk(text=None, finish=None):
    return SimpleNamespace(choices=[SimpleNamespace(
        delta=SimpleNamespace(content=text, reasoning_content=None,
                              tool_calls=None),
        finish_reason=finish)])


def _stream_of(*texts):
    for t in texts:
        yield _chunk(t)


class FallbackStatusTests(unittest.TestCase):
    def _client(self, open_stream):
        import ai.client as ac
        c = ac.AIClient.__new__(ac.AIClient)      # skip key-loading init
        c._client = object()
        c._system_prompt = lambda: "system prompt"
        c._last_user_text = lambda msgs: msgs[-1]["content"]
        c._open_stream = open_stream
        return c

    def _run(self, c):
        return list(c.stream([{"role": "user", "content": "hi"}]))

    def test_fallback_yields_status_not_content(self):
        import ai.client as ac

        def open_stream(model, *a, **k):
            if model == "primary-model":
                raise RuntimeError("model does not exist")
            return _stream_of("Hello there")

        with mock.patch.object(ac, "pick_model",
                               return_value="primary-model"), \
             mock.patch.object(ac, "resolve_client",
                               return_value=object()), \
             mock.patch.object(ac, "FALLBACK_CHAIN", ["backup-model"]), \
             mock.patch.object(ac, "extra_provider_names",
                               return_value=[]), \
             mock.patch.object(ac, "current_mood",
                               return_value=SimpleNamespace(
                                   temperature=0.7, max_tokens=100,
                                   use_reasoner=False,
                                   prefer_fastest=False)):
            pieces = self._run(self._client(open_stream))

        kinds = [k for k, _ in pieces]
        self.assertIn("status", kinds)
        status = next(p for k, p in pieces if k == "status")
        self.assertIn("backup model", status)
        # the marker must never ride as reply content again
        for k, p in pieces:
            if k == "content":
                self.assertNotIn("fallback", p)

    def test_no_fallback_no_status_event(self):
        import ai.client as ac

        with mock.patch.object(ac, "pick_model",
                               return_value="primary-model"), \
             mock.patch.object(ac, "resolve_client",
                               return_value=object()), \
             mock.patch.object(ac, "FALLBACK_CHAIN", ["backup-model"]), \
             mock.patch.object(ac, "extra_provider_names",
                               return_value=[]), \
             mock.patch.object(ac, "current_mood",
                               return_value=SimpleNamespace(
                                   temperature=0.7, max_tokens=100,
                                   use_reasoner=False,
                                   prefer_fastest=False)):
            c = self._client(lambda m, *a, **k: _stream_of("Plain"))
            pieces = self._run(c)

        self.assertEqual([k for k, _ in pieces], ["content"])
        self.assertEqual(pieces[0][1], "Plain")


class SseMappingTests(unittest.TestCase):
    def test_route_maps_status_kind(self):
        # the SSE layer forwards status events as their own key so no
        # consumer mistakes them for deltas
        import routes.api as api
        with open(api.__file__, encoding="utf-8") as f:
            body = f.read()
        self.assertIn('elif kind == "status":', body)
        self.assertIn("'status': payload", body)

    def test_hud_ignores_status_events(self):
        from system.overlay import _sse_piece
        self.assertIsNone(
            _sse_piece('data: {"status": "Switched to backup model"}'))
        self.assertIsNone(
            _sse_piece(b'data: {"status": "Switched to backup model"}'))

    def test_web_logs_status_without_touching_chat(self):
        with open(ROOT / "static" / "js" / "app.js", encoding="utf-8") as f:
            js = f.read()
        self.assertIn("if(obj.status)addLog(", js)
        self.assertNotIn("obj.status){full+=", js)


class PlumbingSanitationTests(unittest.TestCase):
    """Legacy polluted history is cleaned on read and on record."""

    def setUp(self):
        self.saved = []
        self.hist = []
        patches = [
            mock.patch("memory.ensure_session", lambda sid: None),
            mock.patch("memory.save_message",
                       lambda sid, role, text: self.saved.append(
                           (role, text))),
            mock.patch("memory.load_recent_messages",
                       lambda sid, limit=20: list(self.hist)),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_markers_stripped_from_history(self):
        from ai.conversation import ConversationStore
        self.hist = [
            {"role": "user", "content": "hello"},
            {"role": "assistant",
             "content": "[fallback to Mimo ●] [fallback to Mimo ●] "
                        "Hello again — what's next?"},
        ]
        out = ConversationStore().messages_for("s", "hello")
        bodies = [m["content"] for m in out if m["role"] == "assistant"]
        self.assertEqual(bodies, ["Hello again — what's next?"])
        self.assertNotIn("fallback", str(out))

    def test_marker_only_reply_dropped(self):
        from ai.conversation import ConversationStore
        self.hist = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "[fallback to Mimo ●] "},
        ]
        out = ConversationStore().messages_for("s", "hello")
        self.assertEqual([m["role"] for m in out], ["system", "user"])

    def test_record_reply_strips_markers(self):
        from ai.conversation import ConversationStore
        ConversationStore().record_reply(
            "s", "[fallback to Flash ●] The sky is blue.")
        self.assertEqual(self.saved, [("assistant", "The sky is blue.")])

    def test_record_reply_marker_only_not_saved(self):
        from ai.conversation import ConversationStore
        ConversationStore().record_reply("s", "[fallback to Flash ●] ")
        self.assertEqual(self.saved, [])

    def test_plain_reply_untouched(self):
        from ai.conversation import ConversationStore
        ConversationStore().record_reply("s", "The sky is blue.")
        self.assertEqual(self.saved, [("assistant", "The sky is blue.")])

    def test_clean_messages_keeps_metadata_and_order(self):
        from ai.conversation import clean_messages
        rows = [
            {"role": "user", "content": "hello", "created_at": "t1"},
            {"role": "assistant",
             "content": "[fallback to Mimo ●] Hi.", "created_at": "t2"},
            {"role": "tool", "content": "noise", "created_at": "t3"},
        ]
        out = clean_messages(rows)
        self.assertEqual([m["role"] for m in out], ["user", "assistant"])
        self.assertEqual(out[1]["content"], "Hi.")
        self.assertEqual(out[1]["created_at"], "t2")   # metadata kept
        self.assertEqual(rows[1]["content"],
                         "[fallback to Mimo ●] Hi.")   # input untouched


if __name__ == "__main__":
    unittest.main()
