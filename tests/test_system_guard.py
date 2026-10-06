"""system.guard — RAM watchdog hysteresis, alerting, and its skills."""
from __future__ import annotations

import unittest
from unittest import mock

from system import guard


class HysteresisTests(unittest.TestCase):
    def setUp(self):
        guard._armed = True
        guard._fired_count = 0
        guard._last.clear()

    def test_fires_once_then_stays_quiet(self):
        self.assertTrue(guard._should_fire(91, 90))
        # still over threshold but already fired -> silent
        self.assertFalse(guard._should_fire(95, 90))
        self.assertFalse(guard._should_fire(90, 90))

    def test_rearms_only_below_threshold_minus_five(self):
        guard._should_fire(95, 90)
        self.assertFalse(guard._should_fire(87, 90))  # inside hysteresis band
        self.assertFalse(guard._should_fire(84, 90))  # settles, re-arms silently
        self.assertTrue(guard._should_fire(91, 90))   # climbs again -> fires
        self.assertFalse(guard._should_fire(91, 90))  # only once

    def test_under_threshold_never_fires(self):
        self.assertFalse(guard._should_fire(55, 90))
        self.assertEqual(guard._fired_count, 0)


class RunOnceTests(unittest.TestCase):
    def setUp(self):
        guard._armed = True
        guard._fired_count = 0
        guard._last.clear()

    def _snap(self, pct=93):
        return {"percent": pct, "used_gb": 12.1, "total_gb": 16.0,
                "free_gb": 1.4, "cpu": 42.0}

    def test_alerts_with_top_consumer(self):
        fired = []
        with mock.patch.object(guard, "_prefs", return_value=(True, 90)), \
             mock.patch.object(guard, "sample", side_effect=self._snap), \
             mock.patch.object(guard, "top_consumer",
                               return_value=("chrome.exe", 8200)):
            msg = guard.run_once(notify_fn=lambda *a: fired.append(a))
        self.assertTrue(fired)
        self.assertIn("93%", msg)
        self.assertIn("chrome.exe", msg)
        title, body = fired[0]
        self.assertEqual(title, "Memory guard")
        self.assertIn("12.1", body)

    def test_disabled_pref_is_silent(self):
        with mock.patch.object(guard, "_prefs", return_value=(False, 90)), \
             mock.patch.object(guard, "sample", side_effect=self._snap):
            self.assertIsNone(guard.run_once(notify_fn=lambda *a: None))
        self.assertEqual(guard._fired_count, 0)

    def test_healthy_ram_does_not_alert(self):
        with mock.patch.object(guard, "_prefs", return_value=(True, 90)), \
             mock.patch.object(guard, "sample",
                               side_effect=lambda: self._snap(50)):
            self.assertIsNone(guard.run_once(notify_fn=lambda *a: None))

    def test_status_reports_state(self):
        with mock.patch.object(guard, "_prefs", return_value=(True, 85)), \
             mock.patch.object(guard, "sample", side_effect=self._snap):
            s = guard.status()
        self.assertTrue(s["enabled"])
        self.assertEqual(s["threshold"], 85)
        self.assertEqual(s["percent"], 93)


class SkillTests(unittest.TestCase):
    def test_status_skill_answers(self):
        from skills.system_guard import skill_guard
        with mock.patch.object(guard, "status", return_value={
                "enabled": True, "armed": True, "percent": 44,
                "used_gb": 7.0, "total_gb": 16.0, "threshold": 90,
                "fired": 0}):
            out = skill_guard("ram guard status", None)
        self.assertIn("RAM guard", out)
        self.assertIn("44%", out)

    def test_threshold_set_persists(self):
        from skills.system_guard import skill_guard
        with mock.patch("memory.set_pref") as sp, \
             mock.patch.object(guard, "run_once") as rm:
            out = skill_guard("set ram guard to 85", None)
        sp.assert_called_once_with("guard_ram_threshold", 85)
        rm.assert_called_once()
        self.assertIn("85", out)

    def test_threshold_out_of_range_rejected(self):
        from skills.system_guard import skill_guard
        out = skill_guard("set ram guard to 40", None)
        self.assertIn("between 50 and 99", out)

    def test_mic_skill_never_raises(self):
        from skills.system_guard import skill_mic_test
        out = skill_mic_test("mic test", None)
        self.assertIsInstance(out, str)
        self.assertTrue(len(out) > 3)


if __name__ == "__main__":
    unittest.main()
