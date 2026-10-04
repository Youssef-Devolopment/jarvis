"""Onboarding flag: durable pref, default off, round-trips."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import memory.prefs as prefs


class OnboardedPrefTests(unittest.TestCase):
    def setUp(self):
        self._db = prefs._DB
        prefs._DB = Path(tempfile.mkdtemp()) / "prefs.db"

    def tearDown(self):
        prefs._DB = self._db

    def test_default_is_false(self):
        self.assertIn("onboarded", prefs.all_prefs())
        self.assertFalse(prefs.get_pref("onboarded"))

    def test_roundtrip(self):
        self.assertTrue(prefs.set_pref("onboarded", True))
        self.assertTrue(prefs.get_pref("onboarded"))
        self.assertTrue(prefs.set_pref("onboarded", False))
        self.assertFalse(prefs.get_pref("onboarded"))

    def test_unknown_pref_still_rejected(self):
        self.assertFalse(prefs.set_pref("not_a_real_pref", 1))


if __name__ == "__main__":
    unittest.main()
