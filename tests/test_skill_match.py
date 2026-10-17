"""v1.32.0 — skill-routing diagnostics (match_only + last_match).

Dispatch is first-match-wins, so the two honest questions are "which
patterns match this phrase" (conflict detection) and "which skill last
actually answered". match_only must NEVER run a handler — a diagnostic
that fires skills would itself be a hazard.
"""
import unittest

from skills import registry as reg


class MatchOnlyTests(unittest.TestCase):
    def setUp(self):
        self.names = []
        self.calls = []

    def tearDown(self):
        for n in self.names:
            reg.unregister(n)

    def _probe(self, name, pattern, reply="ok"):
        def handler(text, match):
            self.calls.append(name)
            return reply
        reg.register(name, [pattern], "test probe")(handler)
        self.names.append(name)
        return name

    def test_match_only_lists_candidates_and_never_runs(self):
        self._probe("zz_probe_one", r"^zzprobe one$")
        out = reg.match_only("zzprobe one")
        self.assertIn("zz_probe_one", out["candidates"])
        self.assertEqual(out["first"], out["candidates"][0])
        self.assertEqual(self.calls, [])          # handler never ran

    def test_conflict_flagged_when_two_patterns_match(self):
        self._probe("zz_probe_a", r"zzprobe conflict")
        self._probe("zz_probe_b", r"zzprobe conflict")
        out = reg.match_only("zzprobe conflict")
        self.assertTrue(out["conflict"])
        self.assertGreaterEqual(len(out["candidates"]), 2)
        self.assertEqual(self.calls, [])

    def test_no_match_is_empty(self):
        out = reg.match_only("!!! ??? ###")
        self.assertEqual(out["candidates"], [])
        self.assertIsNone(out["first"])
        self.assertFalse(out["conflict"])

    def test_disabled_skill_is_not_a_candidate(self):
        name = self._probe("zz_probe_off", r"^zzprobe off$")
        reg.toggle_skill(name, False)
        self.assertNotIn("zz_probe_off",
                         reg.match_only("zzprobe off")["candidates"])

    def test_dispatch_records_last_match(self):
        self._probe("zz_probe_last", r"^zzprobe last$")
        self.assertEqual(reg.dispatch("zzprobe last"), "ok")
        self.assertEqual(reg.last_match()["skill"], "zz_probe_last")


class SkillMatchRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from server import app
        except Exception as exc:
            raise unittest.SkipTest(f"app import failed: {exc}")
        cls.app = app
        cls.app.testing = True
        cls.client = app.test_client()

    def test_requires_text(self):
        r = self.client.get("/api/skills/match")
        self.assertEqual(r.status_code, 400)

    def test_reports_candidates_and_last(self):
        r = self.client.get("/api/skills/match",
                            query_string={"text": "what time is it"})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("candidates", data)
        self.assertIn("conflict", data)
        self.assertIn("last", data)


if __name__ == "__main__":
    unittest.main()
