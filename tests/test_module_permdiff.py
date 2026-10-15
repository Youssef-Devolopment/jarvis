"""v1.31.0 — module permission diff on update (principle 9).

Before reinstalling/updating a module, CHECK must show what the new
package newly asks for versus the installed manifest: added (amber)
and dropped permissions. Fresh installs report unavailable (nothing
to compare); broken installed manifests report unavailable too —
never a crash, never a silent pass.
"""
import json
import unittest
from pathlib import Path
from unittest import mock

from tests.test_modules import _TempRoot, _manifest, _write_module
import system.modules as modsys


class PermDiffTests(_TempRoot):
    def _installed(self, perms, version="1.0.0"):
        return _write_module(
            self.tmp, _manifest(version=version, permissions=list(perms)))

    def test_added_and_removed(self):
        self._installed(["read:text", "memory"])
        d = modsys.diff_permissions("demo_mod", ["read:text", "network"])
        self.assertTrue(d["available"])
        self.assertEqual(d["current_version"], "1.0.0")
        self.assertEqual(d["added"], ["network"])
        self.assertEqual(d["removed"], ["memory"])

    def test_unchanged_is_empty(self):
        self._installed(["read:text"])
        d = modsys.diff_permissions("demo_mod", ["read:text"])
        self.assertTrue(d["available"])
        self.assertEqual(d["added"], [])
        self.assertEqual(d["removed"], [])

    def test_fresh_install_unavailable(self):
        d = modsys.diff_permissions("never_installed", ["network"])
        self.assertFalse(d["available"])

    def test_broken_installed_manifest_unavailable(self):
        d = self.tmp / "demo_mod"
        d.mkdir(parents=True)
        (d / "module.json").write_text("{oops", encoding="utf-8")
        self.assertFalse(
            modsys.diff_permissions("demo_mod", ["network"])["available"])

    def test_bad_id_unavailable(self):
        self.assertFalse(
            modsys.diff_permissions("../../x", ["network"])["available"])

    def test_validate_path_carries_diff(self):
        self._installed(["read:text"], version="1.0.0")
        parent = Path(self.tmp / "candparent")
        parent.mkdir()
        cand = _write_module(
            parent, _manifest(version="1.1.0",
                              permissions=["read:text", "network"]))
        rep = modsys.validate_path(str(cand))
        self.assertTrue(rep["ok"], rep)
        pd = rep["perm_diff"]
        self.assertTrue(pd["available"])
        self.assertEqual(pd["added"], ["network"])
        self.assertEqual(pd["current_version"], "1.0.0")

    def test_validate_path_fresh_has_no_diff(self):
        parent = Path(self.tmp / "candparent2")
        parent.mkdir()
        cand = _write_module(
            parent, _manifest(id="brand_new_mod",
                             permissions=["read:text"]))
        rep = modsys.validate_path(str(cand))
        self.assertTrue(rep["ok"], rep)
        self.assertFalse(rep["perm_diff"]["available"])


class CheckRenderingTests(unittest.TestCase):
    def test_diff_line_in_check_message(self):
        js = (Path(__file__).resolve().parents[1]
              / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("perm_diff", js)
        self.assertIn("permission changes vs installed", js)
        self.assertIn("permissions unchanged vs installed", js)
        self.assertIn("NEW: ", js)
        self.assertIn("DROPPED: ", js)
        # new permissions warn amber; calm news stays system-colored
        self.assertIn("?'warn':'system')", js)


if __name__ == "__main__":
    unittest.main()
