"""Shell safety rails. Pure functions, nothing executes."""
import tempfile
import unittest

from skills.code_mode import _cmd_safe, _FORBIDDEN
from ai.tools_terminal import _check_command


class ShellGuardTest(unittest.TestCase):
    def test_encoded_command_blocked(self):
        cmd = "powershell -encodedcommand AAA"
        self.assertTrue(any(b in cmd for b in _FORBIDDEN))
        ok, _ = _cmd_safe(cmd)
        self.assertTrue(ok)  # structural pass; blacklist catches it

    def test_multiline_blocked(self):
        ok, reason = _cmd_safe("echo hi\ndel x")
        self.assertFalse(ok)

    def test_null_blocked(self):
        ok, _ = _cmd_safe("echo\x00hi")
        self.assertFalse(ok)

    def test_too_long_blocked(self):
        ok, _ = _cmd_safe("x" * 2001)
        self.assertFalse(ok)

    def test_legit_passes(self):
        for cmd in ("git status", "echo hello", "python --version"):
            ok, _ = _cmd_safe(cmd)
            self.assertTrue(ok, cmd)

    def test_terminal_bans(self):
        self.assertFalse(_check_command("del x")[0])
        self.assertFalse(_check_command("powershell -enc AAA")[0])
        self.assertFalse(_check_command("x" * 2001)[0])
        self.assertTrue(_check_command("git status")[0])


class AdminGateTests(unittest.TestCase):
    def test_locked_without_code_mode(self):
        from skills import code_mode as cm
        from unittest import mock
        with mock.patch.object(cm, "_code_mode_on", return_value=False):
            out = cm.s_run_admin("code run-admin whoami",
                                 _FakeMatch("whoami"))
        self.assertEqual(out, "OVERRIDE is locked.")

    def test_forbidden_never_elevated(self):
        from skills import code_mode as cm
        from unittest import mock
        with mock.patch.object(cm, "_code_mode_on", return_value=True), \
             mock.patch.object(cm, "_ask_admin",
                               side_effect=AssertionError("must not ask")):
            out = cm.s_run_admin("code run-admin format c:",
                                 _FakeMatch("format c:"))
        self.assertIn("never allowed", out)

    def test_decline_runs_nothing(self):
        from skills import code_mode as cm
        from unittest import mock
        with mock.patch.object(cm, "_code_mode_on", return_value=True), \
             mock.patch.object(cm, "_ask_admin", return_value=False), \
             mock.patch.object(cm, "_run_elevated",
                               side_effect=AssertionError("must not run")):
            out = cm.s_run_admin("run whoami as admin",
                                 _FakeMatch("whoami"))
        self.assertIn("not running", out)

    def test_approved_runs_and_returns_output(self):
        from skills import code_mode as cm
        from unittest import mock
        with mock.patch.object(cm, "_code_mode_on", return_value=True), \
             mock.patch.object(cm, "_ask_admin", return_value=True), \
             mock.patch.object(cm, "_run_elevated",
                               return_value=(0, "admin-output")):
            out = cm.s_run_admin("run whoami as admin",
                                 _FakeMatch("whoami"))
        self.assertEqual(out, "admin-output")

    def test_elevated_stages_bat_and_reads_output(self):
        import tempfile
        from pathlib import Path
        from skills import code_mode as cm
        from unittest import mock
        tmp = Path(tempfile.mkdtemp())

        def fake_run(cmd, **kw):
            bats = list(tmp.glob("jarvis-admin-*.bat"))
            self.assertEqual(len(bats), 1)
            self.assertIn("RunAs", cmd[-1])
            (tmp / bats[0].name.replace(".bat", ".out")).write_text(
                "ELEVATED-OK", encoding="utf-8")
            m = mock.MagicMock()
            m.returncode = 0
            m.stderr = ""
            return m

        with mock.patch.object(cm.subprocess, "run", side_effect=fake_run):
            rc, out = cm._run_elevated("whoami", tmpdir=str(tmp))
        self.assertEqual((rc, out), (0, "ELEVATED-OK"))
        self.assertEqual(list(tmp.glob("jarvis-admin-*")), [])

    def test_uac_denial_maps_friendly(self):
        from skills import code_mode as cm
        from unittest import mock
        with mock.patch.object(cm.subprocess, "run",
                               side_effect=OSError("canceled by user")):
            rc, out = cm._run_elevated("whoami", tmpdir=tempfile.mkdtemp())
        self.assertEqual(rc, -1)
        self.assertIn("refused", out.lower())

    def test_patterns(self):
        import re
        pats = [r"^code\s+run-admin\s+(?P<cmd>.+)$",
                r"^code\s+run\s+(?:as\s+admin|elevated)\s+(?P<cmd>.+)$",
                r"^run\s+(?P<cmd>.+?)\s+as\s+(?:admin|administrator)[\?\.\!]?$"]
        for good, cmd in [("code run-admin whoami", "whoami"),
                          ("code run elevated ipconfig", "ipconfig"),
                          ("run notepad as admin", "notepad")]:
            hit = [re.match(p, good, re.IGNORECASE) for p in pats]
            self.assertTrue(any(hit), good)
            self.assertEqual(
                [h for h in hit if h][0].group("cmd"), cmd)
        for bad in ["run admin", "code run whoami", "administrator"]:
            self.assertFalse(any(re.match(p, bad, re.IGNORECASE)
                                 for p in pats), bad)

    def test_as_admin_reaches_elevated_skill_not_launcher(self):
        from skills import code_mode as cm
        from skills import dispatch
        from unittest import mock
        with mock.patch.object(cm, "_code_mode_on", return_value=False):
            out = dispatch("run whoami as admin")
        self.assertEqual(out, "OVERRIDE is locked.")


class _FakeMatch:
    def __init__(self, cmd):
        self._cmd = cmd

    def group(self, name):
        assert name == "cmd"
        return self._cmd


if __name__ == "__main__":
    unittest.main()
