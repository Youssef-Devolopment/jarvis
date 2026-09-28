"""Shell safety rails. Pure functions, nothing executes."""
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


if __name__ == "__main__":
    unittest.main()
