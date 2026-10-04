"""Auto mode: the durable auto_approve_skills pref is a standing yes
for app open/close gates. Refusals (system/self) always apply.
"""
from __future__ import annotations

import unittest
from unittest import mock

from system import app_learner as AL
from system import app_close


class _AutoPref:
    """Force auto_mode() to a fixed value, then restore."""

    def __init__(self, value: bool):
        self.value = value

    def __enter__(self):
        self._p = mock.patch.object(AL, "auto_mode",
                                    return_value=self.value)
        self._p.start()
        return self

    def __exit__(self, *exc):
        self._p.stop()
        return False


class AutoModeTests(unittest.TestCase):
    def test_auto_mode_off_by_default(self):
        with mock.patch("skills.auto_generator.auto_approve_enabled",
                        return_value=False):
            self.assertFalse(AL.auto_mode())

    def test_auto_mode_on(self):
        with mock.patch("skills.auto_generator.auto_approve_enabled",
                        return_value=True):
            self.assertTrue(AL.auto_mode())

    def test_ask_user_standing_yes(self):
        with _AutoPref(True):
            with mock.patch("system.notify.confirm",
                            side_effect=AssertionError("must not prompt")):
                self.assertTrue(AL.ask_user("anything"))

    def test_ask_user_prompts_when_off(self):
        with _AutoPref(False):
            with mock.patch("voice.speak_async", return_value=None), \
                 mock.patch("system.notify.confirm",
                            return_value=True) as cf:
                self.assertTrue(AL.ask_user("discord"))
                cf.assert_called_once()

    def test_skill_template_uses_ask_user(self):
        src = AL._skill_source("Some App", "C:\\x\\app.exe")
        self.assertIn("ask_user", src)
        self.assertIn("ask_fn=ask_user", src)


class LaunchAutoTests(unittest.TestCase):
    def test_learned_repeat_opens_when_auto(self):
        import system.launch as L
        with _AutoPref(True):
            with mock.patch.object(L, "launch_target",
                                   return_value="Opened.") as lt:
                out = AL.launch_learned("C:\\Windows\\System32\\cmd.exe",
                                        "cmd", ask_fn=None)
        self.assertEqual(out, "Opened.")
        lt.assert_called_once()

    def test_learned_repeat_declines_when_manual(self):
        import system.launch as L
        with _AutoPref(False):
            with mock.patch.object(
                    L, "launch_target",
                    side_effect=AssertionError("must not launch")):
                out = AL.launch_learned("C:\\Windows\\System32\\cmd.exe",
                                        "cmd", ask_fn=None)
        self.assertIsNone(out)

    def test_launcher_auto_ask(self):
        from skills import app_launcher
        with _AutoPref(True):
            self.assertTrue(app_launcher._auto_ask("discord"))
        with _AutoPref(False):
            with mock.patch.object(app_launcher, "_ask",
                                   return_value=True) as ask:
                self.assertTrue(app_launcher._auto_ask("discord"))
                ask.assert_called_once_with("discord")


class CloseAutoTests(unittest.TestCase):
    def test_close_skips_prompt_when_auto(self):
        from tests.test_app_close import FakeProc, _fake_psutil
        FakeProc.reset()
        FakeProc(555, "someapp.exe")
        p1, p2 = _fake_psutil()
        p1.start()
        p2.start()
        asked = []
        try:
            with _AutoPref(True):
                with mock.patch("time.sleep", lambda *a, **k: None):
                    res = app_close.close_by_name(
                        "someapp",
                        ask_fn=lambda d: asked.append(d) or False)
        finally:
            p1.stop()
            p2.stop()
            FakeProc.reset()
        self.assertTrue(res["ok"])
        self.assertEqual(asked, [])

    def test_refusal_survives_auto_mode(self):
        from tests.test_app_close import FakeProc, _fake_psutil
        FakeProc.reset()
        FakeProc(4, "svchost.exe")
        p1, p2 = _fake_psutil()
        p1.start()
        p2.start()
        try:
            with _AutoPref(True):
                res = app_close.close_by_name("svchost", ask_fn=None)
            calls = list(FakeProc.registry[4].calls)
        finally:
            p1.stop()
            p2.stop()
            FakeProc.reset()
        self.assertFalse(res["ok"])
        self.assertIn("system process", res["output"])
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
