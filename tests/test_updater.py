"""system.updater — GitHub version check + safe fast-forward self-update."""
from __future__ import annotations

import subprocess
import unittest
from unittest import mock

from system import updater


def _cp(code=0, out="", err=""):
    return subprocess.CompletedProcess([], code, out, err)


def _fake_git(mapping, default=None):
    """Build an _run_git replacement keyed on the argument prefix."""
    def f(args, timeout=None):
        key = " ".join(args)
        for prefix, res in mapping:
            if key.startswith(prefix):
                return res
        return default if default is not None else _cp(1, "", "unexpected: " + key)
    return f


class ParseVersionTests(unittest.TestCase):
    def test_reads_version_line(self):
        self.assertEqual(updater._parse_version('VERSION = "1.9.0"\n'), "1.9.0")

    def test_single_quotes_and_indent(self):
        self.assertEqual(updater._parse_version('  VERSION    = \'2.0.1\''), "2.0.1")

    def test_missing_returns_none(self):
        self.assertIsNone(updater._parse_version("PORT = 5001\n"))


class CheckTests(unittest.TestCase):
    def test_up_to_date(self):
        git = _fake_git([
            ("fetch", _cp(0)),
            ("rev-parse HEAD", _cp(0, "aaa111\n")),
            ("rev-parse origin/main", _cp(0, "aaa111\n")),
        ])
        with mock.patch.object(updater, "_run_git", git):
            res = updater.check()
        self.assertTrue(res["ok"])
        self.assertFalse(res["available"])
        self.assertEqual(res["reason"], "up to date")

    def test_remote_newer_reports_version(self):
        git = _fake_git([
            ("fetch", _cp(0)),
            ("rev-parse HEAD", _cp(0, "aaa111\n")),
            ("rev-parse origin/main", _cp(0, "bbb222\n")),
            ("status", _cp(0, "")),
            ("rev-list", _cp(0, "0\n")),
            ("show", _cp(0, 'VERSION = "1.9.0"\n')),
        ])
        with mock.patch.object(updater, "_run_git", git):
            res = updater.check()
        self.assertTrue(res["ok"])
        self.assertTrue(res["available"])
        self.assertEqual(res["latest"], "1.9.0")
        self.assertFalse(res["dirty"])
        self.assertIn("1.9.0", res["reason"])

    def test_local_commits_never_count_as_update(self):
        git = _fake_git([
            ("fetch", _cp(0)),
            ("rev-parse HEAD", _cp(0, "aaa111\n")),
            ("rev-parse origin/main", _cp(0, "bbb222\n")),
            ("status", _cp(0, "")),
            ("rev-list", _cp(0, "3\n")),
        ])
        with mock.patch.object(updater, "_run_git", git):
            res = updater.check()
        self.assertTrue(res["ok"])
        self.assertFalse(res["available"])
        self.assertIn("local commits", res["reason"])

    def test_dirty_flag_sees_tracked_edits(self):
        git = _fake_git([
            ("fetch", _cp(0)),
            ("rev-parse HEAD", _cp(0, "aaa111\n")),
            ("rev-parse origin/main", _cp(0, "bbb222\n")),
            ("status", _cp(0, " M routes/api.py\n")),
            ("rev-list", _cp(0, "0\n")),
            ("show", _cp(0, 'VERSION = "1.9.0"\n')),
        ])
        with mock.patch.object(updater, "_run_git", git):
            res = updater.check()
        self.assertTrue(res["dirty"])
        self.assertTrue(res["available"])

    def test_fetch_failure_degrades(self):
        git = _fake_git([("fetch", _cp(128, "", "Could not resolve host"))])
        with mock.patch.object(updater, "_run_git", git):
            res = updater.check()
        self.assertFalse(res["ok"])
        self.assertFalse(res["available"])
        self.assertIn("resolve host", res["reason"])

    def test_git_missing_is_not_fatal(self):
        with mock.patch.object(updater.subprocess, "run",
                               side_effect=FileNotFoundError("git")):
            res = updater.check()
        self.assertFalse(res["ok"])
        self.assertIn("git not found", res["reason"])


class UpdateTests(unittest.TestCase):
    def test_refuses_over_dirty_tree(self):
        with mock.patch.object(updater, "_dirty_files",
                               return_value=["config.py"]):
            res = updater.update()
        self.assertFalse(res["ok"])
        self.assertIn("config.py", res["reason"])

    def test_refuses_over_local_commits(self):
        git = _fake_git([
            ("status", _cp(0, "")),
            ("rev-list", _cp(0, "2\n")),
        ])
        with mock.patch.object(updater, "_run_git", git):
            res = updater.update()
        self.assertFalse(res["ok"])
        self.assertIn("local commits", res["reason"])

    def test_clean_tree_fast_forwards(self):
        git = _fake_git([
            ("status", _cp(0, "")),
            ("rev-list", _cp(0, "0\n")),
            ("pull", _cp(0, "Updating aaa111..bbb222\n")),
        ])
        git_mock = mock.MagicMock(side_effect=git)
        with mock.patch.object(updater, "_run_git", git_mock):
            res = updater.update()
        self.assertTrue(res["ok"])
        self.assertIn("restart", res["reason"])
        pull_calls = [a for a, _ in git_mock.call_args_list
                      if " ".join(a[0]).startswith("pull --ff-only")]
        self.assertEqual(len(pull_calls), 1)

    def test_pull_already_current(self):
        git = _fake_git([
            ("status", _cp(0, "")),
            ("rev-list", _cp(0, "0\n")),
            ("pull", _cp(0, "Already up to date.\n")),
        ])
        with mock.patch.object(updater, "_run_git", git):
            res = updater.update()
        self.assertTrue(res["ok"])
        self.assertEqual(res["reason"], "already up to date")

    def test_pull_failure_reports_stderr(self):
        git = _fake_git([
            ("status", _cp(0, "")),
            ("rev-list", _cp(0, "0\n")),
            ("pull", _cp(128, "", "CONFLICT (content)")),
        ])
        with mock.patch.object(updater, "_run_git", git):
            res = updater.update()
        self.assertFalse(res["ok"])
        self.assertIn("CONFLICT", res["reason"])


class BootCheckTests(unittest.TestCase):
    def test_auto_pulls_when_clean(self):
        with mock.patch.object(updater, "check", return_value={
                "ok": True, "current": "1.8.0", "latest": "1.9.0",
                "available": True, "dirty": False, "reason": "new"}), \
             mock.patch.object(updater, "update", return_value={
                "ok": True, "version": "1.9.0", "reason": "done"}) as u, \
             mock.patch.object(updater, "_notify") as n, \
             mock.patch("memory.get_pref", return_value=True):
            updater._boot_check_sync()
        u.assert_called_once()
        self.assertIn("1.9.0", n.call_args[0][0])
        self.assertIn("Restart", n.call_args[0][0])

    def test_dirty_tree_notifies_but_never_pulls(self):
        with mock.patch.object(updater, "check", return_value={
                "ok": True, "current": "1.8.0", "latest": "1.9.0",
                "available": True, "dirty": True, "reason": "new"}), \
             mock.patch.object(updater, "update") as u, \
             mock.patch.object(updater, "_notify") as n, \
             mock.patch("memory.get_pref", return_value=True):
            updater._boot_check_sync()
        u.assert_not_called()
        self.assertIn("local changes", n.call_args[0][0])

    def test_auto_update_off_skips_pull(self):
        with mock.patch.object(updater, "check", return_value={
                "ok": True, "current": "1.8.0", "latest": "1.9.0",
                "available": True, "dirty": False, "reason": "new"}), \
             mock.patch.object(updater, "update") as u, \
             mock.patch.object(updater, "_notify") as n, \
             mock.patch("memory.get_pref", return_value=False):
            updater._boot_check_sync()
        u.assert_not_called()
        self.assertIn("auto-update is off", n.call_args[0][0])

    def test_nothing_to_do_is_silent(self):
        with mock.patch.object(updater, "check", return_value={
                "ok": True, "current": "1.8.0", "latest": "1.8.0",
                "available": False, "dirty": False, "reason": "up to date"}), \
             mock.patch.object(updater, "_notify") as n:
            updater._boot_check_sync()
        n.assert_not_called()

    def test_check_error_does_not_raise(self):
        with mock.patch.object(updater, "check",
                               side_effect=RuntimeError("boom")):
            updater._boot_check_sync()  # must swallow


class EndpointTests(unittest.TestCase):
    """Routes delegate straight to the module — keep the wiring honest."""

    def test_check_and_apply_routes(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover - env without keys
            self.skipTest(f"app import failed: {exc}")
        client = app.test_client()
        with mock.patch.object(updater, "check", return_value={
                "ok": True, "current": "1.8.0", "latest": "1.8.0",
                "available": False, "dirty": False, "reason": "up to date"}):
            r = client.get("/api/update/check")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["reason"], "up to date")
        with mock.patch.object(updater, "update", return_value={
                "ok": False, "version": "1.8.0", "reason": "local changes"}):
            r = client.post("/api/update/apply")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(r.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
