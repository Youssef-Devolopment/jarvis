"""Win theme skill: pattern safety + intent mapping (registry writes
are faked; the live flip is verified by hand, then reverted)."""
from __future__ import annotations

import re
import unittest
from unittest import mock

from skills import win_theme as wt


class WinThemeTests(unittest.TestCase):
    def _match(self, text):
        for p in wt.WIN_THEME_PATTERNS:
            m = re.match(p, text, re.IGNORECASE)
            if m:
                return True
        return False

    def test_matches(self):
        for good in ["switch to dark mode", "turn on light mode",
                     "use dark mode", "turn off transparency",
                     "turn on transparency effects", "disable dark mode"]:
            self.assertTrue(self._match(good), good)

    def test_no_hijack(self):
        for bad in ["dark", "mode", "what is dark matter",
                    "transparent proxy settings"]:
            self.assertFalse(self._match(bad), bad)

    def test_intent_mapping(self):
        calls = []

        def fake_set(name, value):
            calls.append((name, value))
            return True

        with mock.patch.object(wt, "_set_dword",
                               side_effect=fake_set):
            self.assertEqual(wt._apply("switch to dark mode"),
                             "Dark mode on.")
            self.assertIn(("AppsUseLightTheme", 0), calls)
            calls.clear()
            self.assertEqual(wt._apply("turn off dark mode"),
                             "Light mode on.")
            self.assertIn(("AppsUseLightTheme", 1), calls)
            calls.clear()
            self.assertEqual(wt._apply("turn on transparency"),
                             "Transparency effects on.")
            self.assertIn(("EnableTransparency", 1), calls)
            calls.clear()
            self.assertEqual(wt._apply("turn off transparency"),
                             "Transparency effects off.")
            self.assertIn(("EnableTransparency", 0), calls)


if __name__ == "__main__":
    unittest.main()
