"""API input guards: garbage numerics become defaults, never 500s."""
from __future__ import annotations

import unittest

from routes.api import _to_int


class ToIntTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(_to_int("42", 0), 42)
        self.assertEqual(_to_int(7, 0), 7)

    def test_garbage_becomes_default(self):
        for bad in (None, "", "abc", "12.5", [], {}):
            self.assertEqual(_to_int(bad, 60), 60, repr(bad))

    def test_clamps(self):
        self.assertEqual(_to_int(9999, 60, 1, 480), 480)
        self.assertEqual(_to_int(-5, 60, 1, 480), 1)
        self.assertEqual(_to_int(150, 50, 0, 100), 100)


class GuardedEndpointsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def setUp(self):
        from memory import get_pref
        self._saved = {k: get_pref(k) for k in
                       ("personality_preset", "personality_formality",
                        "personality_humor", "personality_verbosity")}

    def tearDown(self):
        from memory import set_pref
        for k, v in self._saved.items():
            try:
                set_pref(k, v)
            except Exception:
                pass
        try:
            self.__class__.client.post("/api/focus/stop")
        except Exception:
            pass

    def test_focus_garbage_minutes(self):
        r = self.__class__.client.post("/api/focus/start",
                                       json={"minutes": "lots"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["minutes"], 60)

    def test_time_summary_garbage_hours(self):
        r = self.__class__.client.get("/api/time/summary?hours=forever")
        self.assertEqual(r.status_code, 200)

    def test_personality_garbage_clamped(self):
        r = self.__class__.client.post(
            "/api/personality/custom",
            json={"formality": "max", "humor": -10, "verbosity": 9999})
        self.assertEqual(r.status_code, 200)
        cur = r.get_json()["current"]
        self.assertTrue(all(0 <= cur[k] <= 100
                            for k in ("formality", "humor", "verbosity")))

    def test_info_exposes_dev_flag(self):
        r = self.__class__.client.get("/api/info")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn("dev", d)
        self.assertIsInstance(d["dev"], bool)


class IndexPageTests(unittest.TestCase):
    """The front page serves with a versioned cache buster so an upgrade
    always loads fresh CSS/JS — no manual hard-refresh needed."""

    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_index_renders(self):
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_static_assets_carry_version_buster(self):
        from config import VERSION
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn("js/app.js?v=%s" % VERSION, html)
        self.assertIn("css/style.css?v=%s" % VERSION, html)


if __name__ == "__main__":
    unittest.main()
