"""workspace_tools interleaver + its API — safe targeted file edits."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills import workspace_tools as wt


class InterleaveTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "sample.py").write_text(
            "def main():\n    return 1\n", encoding="utf-8")
        self._patcher = mock.patch.object(
            wt, "_allowed_roots", return_value=[self.root])
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()
        self._tmp.cleanup()

    def test_append_with_backup(self):
        f = str(self.root / "sample.py")
        out = wt.append_to_file(f, "print('hi')")
        self.assertIn("Appended", out)
        text = (self.root / "sample.py").read_text(encoding="utf-8")
        self.assertIn("print('hi')", text)
        self.assertTrue((self.root / "sample.py.bak").is_file())
        self.assertIn("return 1", text)  # original content preserved

    def test_append_missing_newline_join(self):
        f = self.root / "sample.py"
        f.write_text("line without newline", encoding="utf-8")
        wt.append_to_file(str(f), "second line")
        text = f.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("second line\n"))
        self.assertIn("without newline\nsecond line", text)

    def test_insert_after_anchor(self):
        f = str(self.root / "sample.py")
        out = wt.insert_near(f, "    # ready", "return 1", "after")
        self.assertIn("Inserted after", out)
        lines = (self.root / "sample.py").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines.index("    # ready"),
                         lines.index("    return 1") + 1)

    def test_insert_before_anchor(self):
        f = str(self.root / "sample.py")
        out = wt.insert_near(f, "# header", "def main():", "before")
        self.assertIn("Inserted before", out)
        first = (self.root / "sample.py").read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(first, "# header")

    def test_missing_anchor_reports(self):
        f = str(self.root / "sample.py")
        out = wt.insert_near(f, "x", "no-such-line-here", "after")
        self.assertIn("Anchor not found", out)

    def test_outside_roots_blocked(self):
        out = wt.append_to_file("C:/Windows/not-allowed.txt", "x")
        self.assertTrue(out.startswith("Blocked:"), out)

    def test_missing_file_refused(self):
        out = wt.append_to_file(str(self.root / "ghost.py"), "x")
        self.assertIn("No such file", out)

    def test_skill_dispatch_append(self):
        from skills import dispatch
        f = str(self.root / "sample.py")
        out = dispatch(f"append keep me to file {f}")
        self.assertIsInstance(out, str)
        self.assertIn("keep me", (self.root / "sample.py").read_text())

    def test_api_endpoint(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"app import failed: {exc}")
        client = app.test_client()
        f = str(self.root / "sample.py")
        r = client.post("/api/interleave",
                        json={"path": f, "body": "added via api"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])
        self.assertIn("added via api",
                      (self.root / "sample.py").read_text())
        r2 = client.post("/api/interleave", json={"path": f})
        self.assertEqual(r2.status_code, 400)  # missing body -> ValidationError

    def test_blocked_api_path(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"app import failed: {exc}")
        client = app.test_client()
        r = client.post("/api/interleave",
                        json={"path": "C:/Windows/System32/hosts",
                              "body": "nope"})
        self.assertFalse(r.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
