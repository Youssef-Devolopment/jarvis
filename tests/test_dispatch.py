"""Skill dispatch routing. No launches, no tabs, no network."""
import unittest

from skills import all_skills, dispatch


class DispatchTest(unittest.TestCase):
    def test_expected_skills_registered(self):
        names = {s.name for s in all_skills()}
        for want in ("launch_app", "web_open", "watch_folder",
                     "screen_ocr", "win_click", "win_type",
                     "computer_task", "timer"):
            self.assertIn(want, names, want)

    def test_blocked_scheme_refused(self):
        r = dispatch("open file:///c:/x")
        self.assertIsNotNone(r)
        self.assertIn("Refused", r)

    def test_javascript_refused(self):
        r = dispatch("open javascript:alert(1)")
        self.assertIsNotNone(r)
        self.assertIn("Refused", r)

    def test_unknown_app_no_launch(self):
        r = dispatch("open xyznonexistent123")
        self.assertIsNotNone(r)
        self.assertIn("Could not find", r)

    def test_fuzzy_suggests(self):
        r = dispatch("open notepda")
        self.assertIsNotNone(r)
        self.assertIn("notepad", r.lower())


if __name__ == "__main__":
    unittest.main()
