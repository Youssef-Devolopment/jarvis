"""The recent-turns trail: what the last commands actually did.

`system/turns.py` answers the question the audit log does not — did a
local skill answer that turn or did it go to a model, which one, how
long it took, and whether it failed.
"""
from __future__ import annotations

import unittest


class TurnRingTests(unittest.TestCase):
    def setUp(self):
        from system import turns
        turns.reset()
        self.addCleanup(turns.reset)

    def test_newest_first(self):
        from system import turns
        turns.record("one", "skill", skill="time")
        turns.record("two", "llm", model="deepseek-chat")
        self.assertEqual([t["text"] for t in turns.recent()],
                         ["two", "one"])

    def test_fields_recorded_and_empty_ones_dropped(self):
        from system import turns
        entry = turns.record("hi", "llm", ok=False, ms=123.6,
                             route="fast", model="m", error="boom",
                             skill=None, chars=0)
        self.assertEqual(entry["ms"], 123)          # int(123.6)
        self.assertEqual(entry["source"], "llm")
        self.assertFalse(entry["ok"])
        self.assertEqual(entry["route"], "fast")
        self.assertEqual(entry["error"], "boom")
        self.assertNotIn("skill", entry)            # None is dropped
        self.assertEqual(entry["chars"], 0)         # 0 is not

    def test_verdict_and_extra_ride_along(self):
        from system import turns
        entry = turns.record("no", "llm", verdict="rejected",
                             extra={"agents": True})
        self.assertEqual(entry["verdict"], "rejected")
        self.assertTrue(entry["agents"])

    def test_ring_is_bounded_and_keeps_the_newest(self):
        from system import turns
        for i in range(turns._KEEP + 10):
            turns.record(f"m{i}", "skill")
        got = turns.recent(limit=999)
        self.assertEqual(len(got), turns._KEEP)
        self.assertEqual(got[0]["text"], f"m{turns._KEEP + 9}")

    def test_long_text_is_truncated(self):
        from system import turns
        self.assertEqual(len(turns.record("x" * 500, "skill")["text"]), 160)

    def test_garbage_limit_falls_back(self):
        from system import turns
        turns.record("a", "skill")
        self.assertEqual(len(turns.recent("nonsense")), 1)
        self.assertEqual(len(turns.recent(None)), 1)

    def test_record_never_raises(self):
        from system import turns
        turns.record(None, None)
        self.assertEqual(turns.recent()[0]["source"], "unknown")

    def test_reset_clears_the_ring_and_the_counter(self):
        from system import turns
        turns.record("a", "skill")
        turns.reset()
        self.assertEqual(turns.recent(), [])
        self.assertEqual(turns.record("b", "skill")["n"], 1)


class TurnsEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_endpoint_returns_newest_first(self):
        from system import turns
        turns.reset()
        self.addCleanup(turns.reset)
        turns.record("hello", "skill", skill="say_hi")
        r = self.client.get("/api/turns?limit=5")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["entries"][0]["skill"], "say_hi")

    def test_endpoint_survives_a_garbage_limit(self):
        self.assertEqual(self.client.get("/api/turns?limit=abc").status_code,
                         200)


class CommandRecordsTurnTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_a_skill_command_lands_on_the_trail(self):
        import routes._common as api
        from system import turns
        turns.reset()
        self.addCleanup(turns.reset)
        real_speak = api.speak_async
        api.speak_async = lambda *a, **k: None
        try:
            r = self.client.post("/api/command",
                                 json={"text": "tell me the time"})
        finally:
            api.speak_async = real_speak

        self.assertEqual(r.status_code, 200)
        self.assertIn('"source": "skill"', r.get_data(as_text=True))

        entries = turns.recent()
        self.assertTrue(entries)
        self.assertEqual(entries[0]["source"], "skill")
        self.assertTrue(entries[0].get("skill"))     # the skill is named
        self.assertTrue(entries[0]["ok"])
        self.assertIn("ms", entries[0])


if __name__ == "__main__":
    unittest.main()
