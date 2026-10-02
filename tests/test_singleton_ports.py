"""Tests for the single-instance guard and the port sentinel."""
from __future__ import annotations
import os
import tempfile
import unittest
from pathlib import Path

from ai import ports
from system import singleton


class SingletonGuardTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig_lock = singleton._LOCK
        self._orig_mine = singleton._MINE
        self._orig_check = singleton._pid_is_jarvis
        singleton._LOCK = Path(self._tmp.name) / "jarvis.lock"
        singleton._MINE = False

    def tearDown(self):
        if singleton._MINE:
            singleton.release()
        singleton._LOCK = self._orig_lock
        singleton._MINE = self._orig_mine
        singleton._pid_is_jarvis = self._orig_check
        self._tmp.cleanup()

    def test_acquire_fresh(self):
        self.assertTrue(singleton.acquire())
        self.assertEqual(
            singleton._LOCK.read_text(encoding="utf-8"), str(os.getpid()))
        self.assertTrue(singleton._LOCK.exists())

    def test_refuses_when_live_jarvis_holds_lock(self):
        singleton._pid_is_jarvis = lambda pid: pid == 99999
        singleton._LOCK.write_text("99999", encoding="utf-8")
        self.assertFalse(singleton.acquire())

    def test_stale_lock_is_taken_over(self):
        singleton._pid_is_jarvis = lambda pid: False
        singleton._LOCK.write_text("99999", encoding="utf-8")
        self.assertTrue(singleton.acquire())

    def test_unreadable_lock_is_taken_over(self):
        singleton._LOCK.write_text("not-a-pid", encoding="utf-8")
        self.assertTrue(singleton.acquire())

    def test_release_only_drops_own_lock(self):
        self.assertTrue(singleton.acquire())
        singleton._LOCK.write_text("424242", encoding="utf-8")
        singleton.release()  # not ours anymore -> must not delete
        self.assertTrue(singleton._LOCK.exists())

    def test_current_process_is_not_jarvis(self):
        # this test process runs unittest, not run.py/desktop.py
        self.assertFalse(self._orig_check(os.getpid()))


class PortSentinelTests(unittest.TestCase):
    def test_listeners_shape(self):
        items = ports.list_listeners()
        self.assertIsInstance(items, list)
        self.assertGreater(len(items), 0)
        for item in items[:10]:
            if "error" in item:
                continue
            self.assertIn("port", item)
            self.assertIn("pid", item)
            self.assertIn("process", item)

    def test_kill_rejects_bad_pid(self):
        self.assertFalse(ports.kill_listener("abc")["ok"])
        self.assertFalse(ports.kill_listener(0)["ok"])
        self.assertFalse(ports.kill_listener(-1)["ok"])

    def test_kill_refuses_self(self):
        r = ports.kill_listener(os.getpid())
        self.assertFalse(r["ok"])
        self.assertIn("myself", r["error"])

    def test_kill_refuses_system_pid(self):
        r = ports.kill_listener(4)
        self.assertFalse(r["ok"])
        self.assertIn("system", r["error"])

    def test_kill_missing_pid(self):
        # pick a pid that almost certainly isn't running
        import psutil
        dead = None
        for cand in range(49000, 49050):
            if not psutil.pid_exists(cand):
                dead = cand
                break
        if dead is None:
            self.skipTest("no free pid found")
        r = ports.kill_listener(dead, port=9)
        self.assertFalse(r["ok"])


if __name__ == "__main__":
    unittest.main()
