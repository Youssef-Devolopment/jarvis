"""v1.22.0 — surgical workspace edits + mandatory self-verification.

JARVIS must behave like a careful agent: edit files with an exact
match instead of rewriting whole files, and NEVER claim an edit it
did not verify.  fs_write / fs_append / fs_replace append a verify
verdict for code files (.py compiled in-process, .json parsed, .js
checked via `node --check`); everything else stays quiet.  A failed
verification is reported loudly so the model fixes its own breakage
in the next loop round.
"""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


class _Base(unittest.TestCase):
    def setUp(self):
        from ai import tools_fs as tfs
        self.tfs = tfs
        self.root = Path(tempfile.mkdtemp())
        self.bak = self.root / "backups"
        self.bak.mkdir()
        p1 = mock.patch.object(tfs, "_ALLOWED_ROOTS", [self.root])
        p2 = mock.patch.object(tfs, "_BACKUPS", self.bak)
        p1.start(); self.addCleanup(p1.stop)
        p2.start(); self.addCleanup(p2.stop)

    def _file(self, name, text):
        p = self.root / name
        p.write_text(text, encoding="utf-8")
        return p


class FsReplaceTests(_Base):
    def test_single_occurrence_replaced_and_verified(self):
        p = self._file("app.py", "x = 1\nprint(x)\n")
        out = self.tfs.fs_replace(str(p), "x = 1", "x = 42")
        self.assertIn("[ok] replaced 1 occurrence(s)", out)
        self.assertIn("verify: ok (syntax)", out)
        self.assertEqual(p.read_text(encoding="utf-8"), "x = 42\nprint(x)\n")

    def test_ambiguous_match_refused_without_flag(self):
        p = self._file("a.txt", "foo bar foo")
        out = self.tfs.fs_replace(str(p), "foo", "baz")
        self.assertIn("[ambiguous] 2 occurrences", out)
        # nothing changed
        self.assertEqual(p.read_text(encoding="utf-8"), "foo bar foo")

    def test_replace_all_touches_every_match(self):
        p = self._file("a.txt", "foo bar foo")
        out = self.tfs.fs_replace(str(p), "foo", "baz", replace_all=True)
        self.assertIn("[ok] replaced 2 occurrence(s)", out)
        self.assertEqual(p.read_text(encoding="utf-8"), "baz bar baz")

    def test_old_text_missing_is_not_found(self):
        p = self._file("a.txt", "hello")
        self.assertIn("[not found]",
                      self.tfs.fs_replace(str(p), "nope", "x"))

    def test_empty_old_refused(self):
        p = self._file("a.txt", "hello")
        self.assertIn("[error]", self.tfs.fs_replace(str(p), "", "x"))

    def test_path_outside_roots_blocked(self):
        out = self.tfs.fs_replace("C:/Windows/system.ini", "a", "b")
        self.assertIn("[blocked]", out)

    def test_existing_file_backed_up_before_write(self):
        p = self._file("a.txt", "old content")
        self.tfs.fs_replace(str(p), "old", "new")
        saved = list(self.bak.iterdir())
        self.assertEqual(len(saved), 1)
        self.assertIn("old content",
                      (saved[0]).read_text(encoding="utf-8", errors="replace"))


class VerifyAfterEditTests(_Base):
    def test_write_valid_python_verified(self):
        out = self.tfs.fs_write(str(self.root / "ok.py"), "x = 1\n")
        self.assertIn("[ok] wrote", out)
        self.assertIn("verify: ok (syntax)", out)

    def test_write_broken_python_flags_failure(self):
        out = self.tfs.fs_write(str(self.root / "bad.py"), "def broken(:\n")
        self.assertIn("[ok] wrote", out)          # the write itself worked
        self.assertIn("VERIFY FAILED", out)
        self.assertIn("invalid syntax", out)
        # next round can read the file and fix it
        self.assertTrue((self.root / "bad.py").exists())

    def test_write_json_valid_and_broken(self):
        ok = self.tfs.fs_write(str(self.root / "c.json"), '{"a": 1}')
        self.assertIn("verify: ok (json)", ok)
        bad = self.tfs.fs_write(str(self.root / "d.json"), "{nope")
        self.assertIn("VERIFY FAILED", bad)

    def test_write_plain_text_has_no_verify_suffix(self):
        out = self.tfs.fs_write(str(self.root / "note.md"), "just text")
        self.assertIn("[ok] wrote", out)
        self.assertNotIn("verify", out)

    def test_append_that_breaks_python_is_flagged(self):
        p = self._file("good.py", "x = 1\n")
        out = self.tfs.fs_append(str(p), "def x(:\n")
        self.assertIn("[ok] appended", out)
        self.assertIn("VERIFY FAILED", out)

    def test_js_verified_via_node_check(self):
        with mock.patch.object(
                self.tfs.subprocess, "run",
                return_value=SimpleNamespace(returncode=0, stderr="",
                                             stdout="")):
            out = self.tfs.fs_write(str(self.root / "a.js"), "let x = 1;")
        self.assertIn("verify: ok (syntax)", out)

    def test_js_syntax_error_reported(self):
        with mock.patch.object(
                self.tfs.subprocess, "run",
                return_value=SimpleNamespace(
                    returncode=1, stdout="",
                    stderr="a.js:1\nSyntaxError: unexpected token\n")):
            out = self.tfs.fs_write(str(self.root / "b.js"), "let x = ;")
        self.assertIn("VERIFY FAILED", out)
        self.assertIn("SyntaxError", out)

    def test_js_without_node_skips_gracefully(self):
        with mock.patch.object(self.tfs.subprocess, "run",
                               side_effect=FileNotFoundError("node")):
            out = self.tfs.fs_write(str(self.root / "c.js"), "let x = 1;")
        self.assertIn("verify skipped (node not installed)", out)


class ReplaceWiringTests(_Base):
    def test_dispatch_routes_fs_replace(self):
        from ai.tools import execute_tool
        p = self._file("s.txt", "alpha beta")
        out = execute_tool("fs_replace", {"path": str(p),
                                          "old": "beta", "new": "gamma"})
        self.assertIn("[ok] replaced 1 occurrence(s)", out)
        self.assertEqual(p.read_text(encoding="utf-8"), "alpha gamma")

    def test_replace_is_approval_gated_in_os_mode(self):
        # a mutation tool must never run free in the autonomous loop
        from ai.os_mode import AUTO_TOOLS
        self.assertNotIn("fs_replace", AUTO_TOOLS)

    def test_schema_present_and_counts_as_31(self):
        from ai.tools import TOOL_SCHEMAS
        fns = {t["function"]["name"]: t["function"] for t in TOOL_SCHEMAS}
        self.assertIn("fs_replace", fns)
        self.assertEqual(fns["fs_replace"]["parameters"]["required"],
                         ["path", "old", "new"])
        # README/landing page say "31 built-in tools" — update together
        self.assertEqual(len(fns), 31)


if __name__ == "__main__":
    unittest.main()
