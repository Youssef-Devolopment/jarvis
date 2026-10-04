"""Skill isolation: one broken module or pattern can never take
down the package, the dispatch, or the server boot.
"""
from __future__ import annotations

import unittest

from skills import _load_modules
from skills.base import Skill


class LoaderTests(unittest.TestCase):
    def test_bogus_module_does_not_raise(self):
        loaded, failed = _load_modules(["clock", "no_such_skill_xyz"])
        self.assertIn("clock", loaded)
        self.assertIn("no_such_skill_xyz", failed)

    def test_package_still_dispatches(self):
        from skills import dispatch
        out = dispatch("tell me the time")
        self.assertIsNotNone(out)
        self.assertIn("It is ", out)


class MatchGuardTests(unittest.TestCase):
    def test_raising_pattern_is_skipped(self):
        class Boom:
            def search(self, text):
                raise RuntimeError("bad pattern")

        s = Skill(name="probe", patterns=[Boom()], handler=lambda t, m: "x")
        self.assertIsNone(s.match("anything"))

    def test_failing_handler_falls_through(self):
        from skills import registry

        @registry.register("zz_probe_fail", [r"^zz probe fail$"],
                           "probe", front=True)
        def _probe(text, match):
            raise RuntimeError("handler down")

        try:
            self.assertIsNone(registry.dispatch("zz probe fail"))
        finally:
            registry.unregister("zz_probe_fail")


if __name__ == "__main__":
    unittest.main()
