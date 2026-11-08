"""The community-plugin sandbox.

plugins/__init__.py is the only thing standing between a dropped .py
file and an arbitrary import — and before this file existed it had zero
test coverage (no test imported `plugins` at all). These pin the rules
the README promises: allowed imports, no eval/subprocess/sockets, a
well-formed skill name, and a rejection reason the user can read.

Everything runs against a temporary plugins package so the suite never
writes into the real plugins/ directory.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import plugins
from skills.registry import all_skills, unregister

VALID = (
    "from skills.registry import register\n"
    '@register("sandbox_ok", [r"^sandbox ok$"], "demo")\n'
    "def s(text, match):\n    return 'ok'"
)

# skill names these tests may register, torn down after every test
TEST_SKILLS = ("sandbox_ok", "probe_good")


def _cleanup():
    for name in TEST_SKILLS:
        unregister(name)
    # only the modules these tests created — never the shipped ones
    for mod in [m for m in list(sys.modules)
                if m.startswith(("plugins.probe_", "plugins.sandbox_"))]:
        sys.modules.pop(mod, None)


class _SandboxedPlugins(unittest.TestCase):
    """Points the plugins package at a scratch directory."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis-plugin-"))
        self._patchers = [
            mock.patch.object(plugins, "__path__", [str(self.tmp)]),
            mock.patch.object(plugins, "_loaded", []),
            mock.patch.object(plugins, "_failed", []),
        ]
        for p in self._patchers:
            p.start()

    def tearDown(self):
        for p in reversed(self._patchers):
            p.stop()
        _cleanup()


class InstallRejectionTests(_SandboxedPlugins):
    """Every rejection must name the rule that fired."""

    def assertRejected(self, code, fragment, name="probe"):
        r = plugins.install_plugin(name, code)
        self.assertIn("error", r, f"expected rejection, got {r}")
        self.assertIn(fragment, r["error"])
        return r

    def test_allowed_imports_are_accepted(self):
        from skills.auto_generator import _validate
        meta = _validate(VALID)          # validate only: no import, no
        self.assertEqual(meta["name"], "sandbox_ok")   # skill registered
        r = plugins.install_plugin("sandbox_probe_ok", VALID)
        self.assertNotIn("error", r, r)
        self.assertEqual(r["skill"], "sandbox_ok")
        self.assertTrue((self.tmp / "sandbox_probe_ok.py").exists())

    def test_subprocess_is_blocked(self):
        self.assertRejected(
            "import subprocess\n" + VALID, "blocked import: subprocess")

    def test_os_is_blocked(self):
        self.assertRejected("import os\n" + VALID, "blocked import: os")

    def test_socket_is_blocked(self):
        self.assertRejected("import socket\n" + VALID,
                            "blocked import: socket")

    def test_eval_is_blocked(self):
        self.assertRejected(VALID + "\neval('1')", "blocked call: eval()")

    def test_exec_is_blocked(self):
        self.assertRejected(VALID + "\nexec('1')", "blocked call: exec()")

    def test_open_is_blocked(self):
        self.assertRejected(
            "from skills.registry import register\nopen('/etc/passwd')\n"
            '@register("sandbox_open", [r"^so$"], "d")\n'
            "def s(t, m):\n    return 1", "blocked call: open()")

    def test_missing_register_is_reported(self):
        self.assertRejected("def s(t, m):\n    return 1", "@register")

    def test_bad_skill_name_is_reported(self):
        code = ("from skills.registry import register\n"
                '@register("BAD NAME", [r"^q$"], "d")\n'
                "def s(t, m):\n    return 1")
        self.assertRejected(code, "bad skill name")

    def test_too_many_patterns_is_reported(self):
        """One list literal holding six patterns — the shape the README
        documents (1-5 literal regex patterns)."""
        pats = "[" + ", ".join(f'"p{i}"' for i in range(6)) + "]"
        code = ("from skills.registry import register\n"
                f'@register("sandbox_many", {pats}, "d")\n'
                "def s(t, m):\n    return 1")
        r = plugins.install_plugin("probe_many", code)
        self.assertIn("error", r, r)
        self.assertIn("1-5 regex patterns", r["error"])

    def test_bad_regex_is_reported(self):
        code = ("from skills.registry import register\n"
                '@register("sandbox_regex", ["(["], "d")\n'
                "def s(t, m):\n    return 1")
        r = plugins.install_plugin("probe_regex", code)
        self.assertIn("error", r, r)
        self.assertIn("bad regex", r["error"])

    def test_syntax_error_is_reported(self):
        self.assertRejected("this is not python (", "syntax error")

    def test_malformed_plugin_name_is_reported(self):
        r = plugins.install_plugin("BAD NAME", VALID)
        self.assertIn("error", r)
        self.assertIn("bad plugin name", r["error"])

    def test_duplicate_name_is_reported(self):
        (self.tmp / "hello.py").write_text(VALID, encoding="utf-8")
        r = plugins.install_plugin("hello", VALID)
        self.assertIn("error", r)
        self.assertIn("already exists", r["error"])

    def test_missing_code_is_reported(self):
        r = plugins.install_plugin("probe_nocode", "")
        self.assertIn("error", r)

    def test_nothing_is_written_when_validation_fails(self):
        before = sorted(p.name for p in self.tmp.glob("*.py"))
        for code in ("import subprocess\n" + VALID,
                     "def s(t, m):\n    return 1"):
            plugins.install_plugin("probe_never_written", code)
        self.assertEqual(before, sorted(p.name for p in self.tmp.glob("*.py")))

    def test_failed_install_leaves_no_module_behind(self):
        r = plugins.install_plugin("probe_half", "def s(t, m):\n    return 1")
        self.assertIn("error", r)
        self.assertNotIn("plugins.probe_half", sys.modules)


class LoaderTests(_SandboxedPlugins):
    """load_plugins() must report WHY it refused a file."""

    def test_valid_plugin_loads(self):
        (self.tmp / "probe_good.py").write_text(VALID, encoding="utf-8")
        r = plugins.load_plugins()
        self.assertIn("plugins.probe_good", r["loaded"])
        self.assertEqual(r["failed"], [])

    def test_rejected_plugin_is_reported_with_a_reason(self):
        (self.tmp / "probe_bad.py").write_text(
            "import subprocess\n" + VALID, encoding="utf-8")
        r = plugins.load_plugins()
        self.assertNotIn("plugins.probe_bad", r["loaded"])
        self.assertEqual(len(r["failed"]), 1)
        self.assertEqual(r["failed"][0]["file"], "probe_bad")
        self.assertIn("blocked import: subprocess", r["failed"][0]["error"])

    def test_rejected_plugin_is_never_imported(self):
        (self.tmp / "probe_bad.py").write_text(
            "import subprocess\n" + VALID, encoding="utf-8")
        plugins.load_plugins()
        self.assertNotIn("plugins.probe_bad", sys.modules)

    def test_underscore_prefixed_files_are_skipped(self):
        (self.tmp / "_template_copy.py").write_text(VALID, encoding="utf-8")
        r = plugins.load_plugins()
        self.assertEqual(r["failed"], [])
        self.assertNotIn("plugins._template_copy", r["loaded"])

    def test_status_exposes_failures(self):
        (self.tmp / "probe_bad.py").write_text(
            "def s(t, m):\n    return 1", encoding="utf-8")
        plugins.load_plugins()
        st = plugins.status()
        self.assertTrue(st["failed"])
        self.assertIn("error", st["failed"][0])


class StatusShapeTests(unittest.TestCase):
    def test_status_has_the_keys_the_ui_reads(self):
        st = plugins.status()
        for key in ("loaded", "failed", "skill_count"):
            self.assertIn(key, st)
        self.assertIsInstance(st["skill_count"], int)

    def test_shipped_example_plugin_validates(self):
        """hello.py is the documented template — it must stay legal."""
        from skills.auto_generator import _validate
        src = Path("plugins/hello.py").read_text(encoding="utf-8")
        meta = _validate(src)
        self.assertTrue(meta["name"])

    def test_shipped_template_validates(self):
        from skills.auto_generator import _validate
        src = Path("plugins/_template.py").read_text(encoding="utf-8")
        meta = _validate(src)
        self.assertTrue(meta["name"])

    def test_every_shipped_plugin_passes_the_sandbox(self):
        from skills.auto_generator import _validate
        for path in sorted(Path("plugins").glob("*.py")):
            if path.name.startswith("_"):
                continue
            meta = _validate(path.read_text(encoding="utf-8"))
            self.assertTrue(meta["name"], path.name)

    def test_the_suite_does_not_register_test_skills(self):
        """Guard against a test leaking a skill into the registry."""
        names = {s.name for s in all_skills()}
        for name in TEST_SKILLS:
            self.assertNotIn(name, names, name)


if __name__ == "__main__":
    unittest.main()
