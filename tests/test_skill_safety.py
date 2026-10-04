"""Skill-maker pattern safety: catch-alls, empty-matchers, broad and
cloned patterns are rejected at validation; legit skills pass."""
from __future__ import annotations

import unittest

from skills import auto_generator as ag


def _code(name, pattern):
    return (
        "from skills.registry import register\n"
        f"@register({name!r}, [{pattern!r}], \"probe\")\n"
        "def zz_probe_x(text, match):\n"
        "    return \"pong\"\n"
    )


class PatternSafetyTests(unittest.TestCase):
    def test_catch_all_rejected(self):
        for p in [r".*", r".+", r"^.*$", r"^(.+)$"]:
            with self.assertRaises(ValueError, msg=p):
                ag._validate(_code("zz_probe_catch", p))

    def test_empty_matcher_rejected(self):
        with self.assertRaises(ValueError):
            ag._validate(_code("zz_probe_empty", r"(note)?( .*)?"))

    def test_broad_corpus_hijack_rejected(self):
        with self.assertRaises(ValueError):
            ag._validate(_code("zz_probe_broad", r"\b(open|close|timer)\b"))

    def test_clone_of_existing_skill_rejected(self):
        with self.assertRaises(ValueError):
            ag._validate(_code("zz_probe_clone",
                               r"\bwhat\s+time\s+is\s+it\b"))

    def test_specific_skill_passes(self):
        meta = ag._validate(_code("zz_probe_ok", r"^ping the gate$"))
        self.assertEqual(meta["name"], "zz_probe_ok")

    def test_same_name_refresh_allowed(self):
        meta = ag._validate(_code("time", r"\bwhat\s+time\s+is\s+it\b"))
        self.assertEqual(meta["name"], "time")

    def test_trusted_app_template_passes(self):
        code = (
            "from skills.registry import register\n"
            "import system\n"
            "@register(\"app_frob\", "
            "[r\"^(?:open|launch|start|run)\\s+(?:the\\s+)?(?:app\\s+)?"
            "frob[\\?\\.\\!]?$\"], \"Open frob\")\n"
            "def app_frob(text, match):\n"
            "    return \"Opened.\"\n"
        )
        meta = ag._validate(code, trusted=True)
        self.assertEqual(meta["name"], "app_frob")


if __name__ == "__main__":
    unittest.main()
