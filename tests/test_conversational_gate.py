"""Conversational gate: chit-chat skips skills, tasks do not.

The gate in `ai/self_awareness.py` SKIPS the skill dispatcher entirely,
so anything a local skill matches must never be classified as chit-chat.
"what time is it" used to be, which turned the most natural way to ask
into a full model round trip (measured live: 35s vs 3ms for the skill).
"""
from __future__ import annotations

import unittest


class GateTests(unittest.TestCase):
    def test_chitchat_still_skips_skills(self):
        from ai.self_awareness import is_conversational
        for text in ("hi", "hello there", "thanks", "how are you",
                     "what can you do", "good night", "what's your name"):
            self.assertTrue(is_conversational(text), text)

    def test_task_phrasings_local_skills_answer_are_let_through(self):
        from ai.self_awareness import is_conversational
        for text in ("what time is it", "what's the time",
                     "what is the time", "what day is it",
                     "what date is it", "tell me the time"):
            self.assertFalse(is_conversational(text), text)

    def test_very_short_input_is_still_conversational(self):
        from ai.self_awareness import is_conversational
        self.assertTrue(is_conversational("ok"))

    def test_empty_input_is_not_conversational(self):
        from ai.self_awareness import is_conversational
        self.assertFalse(is_conversational("   "))


class GateEndToEndTests(unittest.TestCase):
    """A phrasing the local time skill matches must reach that skill."""

    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def _post(self, text):
        import routes._common as api
        real_speak = api.speak_async
        api.speak_async = lambda *a, **k: None
        try:
            return self.client.post("/api/command", json={"text": text})
        finally:
            api.speak_async = real_speak

    def test_what_time_is_it_hits_the_local_skill(self):
        from system import turns
        turns.reset()
        self.addCleanup(turns.reset)

        r = self._post("what time is it")
        self.assertEqual(r.status_code, 200)
        self.assertIn('"source": "skill"', r.get_data(as_text=True))

        entry = turns.recent()[0]
        self.assertEqual(entry["source"], "skill")
        self.assertEqual(entry["skill"], "time")
        self.assertLess(entry["ms"], 2000)   # a skill, not a model call

    def test_what_day_is_it_hits_the_date_skill(self):
        from system import turns
        turns.reset()
        self.addCleanup(turns.reset)

        r = self._post("what day is it")
        self.assertEqual(r.status_code, 200)
        self.assertIn('"source": "skill"', r.get_data(as_text=True))
        self.assertEqual(turns.recent()[0]["skill"], "date")


if __name__ == "__main__":
    unittest.main()
