"""notify.alert — desktop toast + HUD pulse for finished background jobs."""
from __future__ import annotations

import unittest
from unittest import mock


class AlertTests(unittest.TestCase):
    def test_alert_toasts_and_pulses(self):
        from system import notify
        with mock.patch.object(notify, "toast", return_value=True) as t, \
             mock.patch("system.overlay.notice") as n:
            out = notify.alert("Research ready", "topic x")
        self.assertTrue(out)
        t.assert_called_once_with("Research ready", "topic x")
        n.assert_called_once()
        self.assertIn("Research ready", n.call_args[0][0])

    def test_alert_handles_missing_hud(self):
        from system import notify
        with mock.patch.object(notify, "toast", return_value=False), \
             mock.patch("system.overlay.notice",
                        side_effect=RuntimeError("no hud")):
            self.assertFalse(notify.alert("T", "m"))

    def test_alert_title_only(self):
        from system import notify
        with mock.patch.object(notify, "toast", return_value=True) as t, \
             mock.patch("system.overlay.notice") as n:
            notify.alert("Timer done")
        t.assert_called_once_with("Timer done", "")
        self.assertIn("Timer done", n.call_args[0][0])

    def test_notice_without_hud_is_noop(self):
        from system import overlay
        overlay.notice("should neither raise nor queue")


if __name__ == "__main__":
    unittest.main()
