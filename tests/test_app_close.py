"""Close-app skill: pattern safety, resolution, refusal guards,
graceful-then-force kill — all against faked processes, never real ones.
"""
from __future__ import annotations

import re
import unittest
from unittest import mock

from system import app_close
from skills.app_closer import CLOSE_PATTERNS


class FakeProc:
    registry = {}

    def __init__(self, pid, name, cmd=(), stubborn=False):
        self.pid = pid
        self._name = name
        self._cmd = list(cmd)
        self._dead = False
        self.stubborn = stubborn
        self.calls = []
        FakeProc.registry[pid] = self

    def name(self):
        return self._name

    def cmdline(self):
        return self._cmd

    def exe(self):
        return "C:\\fake\\" + self._name

    def terminate(self):
        self.calls.append("terminate")
        if not self.stubborn:
            self._dead = True

    def kill(self):
        self.calls.append("kill")
        self._dead = True

    def wait(self, timeout=None):
        return None

    def is_running(self):
        return not self._dead

    @classmethod
    def reset(cls):
        cls.registry = {}


def _fake_psutil():
    import psutil
    return mock.patch.object(
        psutil, "process_iter", lambda *a, **k: list(FakeProc.registry.values())
    ), mock.patch.object(
        psutil, "Process",
        lambda pid: FakeProc.registry[pid]
        if pid in FakeProc.registry
        else (_ for _ in ()).throw(psutil.NoSuchProcess(pid)),
    )


class PatternTests(unittest.TestCase):
    def _match(self, text):
        for p in CLOSE_PATTERNS:
            m = re.match(p, text, re.IGNORECASE)
            if m:
                return m.group("app")
        return None

    def test_matches_app_names(self):
        self.assertEqual(self._match("close notepad"), "notepad")
        self.assertEqual(self._match("kill chrome"), "chrome")
        self.assertEqual(self._match("close the calculator"), "calculator")

    def test_never_hijacks_tab_or_window(self):
        for t in ["close tab", "close the tab", "close window",
                  "close the window", "kill tab"]:
            self.assertIsNone(self._match(t), t)


class CloseEngineTests(unittest.TestCase):
    def setUp(self):
        FakeProc.reset()
        self._learned = app_close._learned_map
        app_close._learned_map = lambda: {}
        p1, p2 = _fake_psutil()
        self._pp1 = p1
        self._pp2 = p2
        p1.start()
        p2.start()
        self._sleep = mock.patch("time.sleep", lambda *a, **k: None)
        self._sleep.start()

    def tearDown(self):
        app_close._learned_map = self._learned
        self._pp1.stop()
        self._pp2.stop()
        self._sleep.stop()
        FakeProc.reset()

    def _asked(self, answer):
        self.asked = []
        def ask(display):
            self.asked.append(display)
            return answer
        return ask

    def test_close_running_alias_app_without_asking(self):
        FakeProc(111, "notepad.exe")
        res = app_close.close_by_name("notepad", ask_fn=self._asked(True))
        self.assertTrue(res["ok"])
        self.assertIn("Closed notepad", res["output"])
        self.assertEqual(self.asked, [])
        self.assertIn("terminate", FakeProc.registry[111].calls)

    def test_not_running(self):
        res = app_close.close_by_name("vlc", ask_fn=self._asked(True))
        self.assertFalse(res["ok"])
        self.assertIn("isn't running", res["output"])

    def test_refuses_system_process(self):
        FakeProc(4, "svchost.exe")
        res = app_close.close_by_name("svchost", ask_fn=self._asked(True))
        self.assertFalse(res["ok"])
        self.assertIn("system process", res["output"])
        self.assertEqual(FakeProc.registry[4].calls, [])

    def test_refuses_itself(self):
        FakeProc(999, "pythonw.exe",
                 cmd=("C:\\x\\.venv\\Scripts\\pythonw.exe", "desktop.py"))
        res = app_close.close_by_name(
            "pythonw", ask_fn=self._asked(True))
        # pythonw is unknown-instant only if running match is self
        self.assertFalse(res["ok"])
        self.assertEqual(FakeProc.registry[999].calls, [])

    def test_non_instant_needs_confirm(self):
        FakeProc(222, "someapp.exe")
        res = app_close.close_by_name("someapp", ask_fn=self._asked(False))
        self.assertFalse(res.get("ok"))
        self.assertTrue(res.get("declined"))
        self.assertEqual(FakeProc.registry[222].calls, [])
        res2 = app_close.close_by_name("someapp", ask_fn=self._asked(True))
        self.assertTrue(res2["ok"])

    def test_stubborn_app_gets_forced(self):
        FakeProc(333, "notepad.exe", stubborn=True)
        res = app_close.close_by_name("notepad", ask_fn=self._asked(True))
        self.assertTrue(res["ok"])
        self.assertIn("kill", FakeProc.registry[333].calls)

    def test_learned_app_resolves_by_display_name(self):
        app_close._learned_map = lambda: {"my cool app": "coolapp.exe"}
        FakeProc(444, "coolapp.exe")
        res = app_close.close_by_name("my cool app",
                                      ask_fn=self._asked("BOOM"))
        self.assertTrue(res["ok"])
        self.assertEqual(self.asked, [])


class CloseApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_close_unknown_app_404(self):
        r = self.__class__.client.post(
            "/api/apps/close", json={"query": "definitely-not-an-app-xyz"})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(r.get_json()["ok"])

    def test_close_missing_query_400(self):
        r = self.__class__.client.post("/api/apps/close", json={})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
