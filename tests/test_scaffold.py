"""workspace_tools.scaffold — Boilerplate Scaffolder."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skills import workspace_tools as wt


class ScaffoldTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name) / "projects"
        self._patcher = mock.patch.object(
            wt, "_allowed_roots", return_value=[self.root])
        self._patcher.start()
        self._proj = mock.patch.object(wt, "_PROJECTS", self.root)
        self._proj.start()

    def tearDown(self):
        self._proj.stop()
        self._patcher.stop()
        self._tmp.cleanup()

    def test_flask_tree_is_runnable_shape(self):
        out = wt.scaffold("flask", "Task Board")
        self.assertIn("flask", out)
        target = self.root / "task-board"
        for rel in ("README.md", "app.py", "requirements.txt",
                    ".env.example", "tests/test_app.py", ".gitignore"):
            self.assertTrue((target / rel).is_file(), rel)
        self.assertNotIn("__NAME__", (target / "README.md").read_text())  # replaced
        self.assertNotIn("__NAME__", (target / "app.py").read_text())

    def test_name_is_slugified(self):
        out = wt.scaffold("python", "My Cool App 2!")
        self.assertIn("my-cool-app-2", out)
        self.assertTrue((self.root / "my-cool-app-2" / "main.py").is_file())

    def test_kind_fallback_and_node_alias(self):
        out = wt.scaffold("javascript", "tinytool")
        self.assertIn("node", out)  # javascript aliases to node
        self.assertTrue((self.root / "tinytool" / "package.json").is_file())
        out2 = wt.scaffold("weird", "other")
        self.assertIn("python", out2)  # unknown kinds fall back to python

    def test_existing_target_refused(self):
        wt.scaffold("plain", "dup")
        out = wt.scaffold("plain", "dup")
        self.assertIn("Already exists", out)

    def test_outside_roots_blocked(self):
        out = wt.scaffold("plain", "intruder",
                          parent=Path("C:/definitely/not/allowed/elsewhere"))
        self.assertTrue(out.startswith("Blocked:"), out)

    def test_skill_parses_kind_and_name(self):
        from skills import dispatch
        with mock.patch.object(wt, "_PROJECTS", self.root):
            out = dispatch("scaffold a flask project called taskboard")
        self.assertIsInstance(out, str)
        self.assertIn("taskboard", out)
        self.assertTrue((self.root / "taskboard" / "app.py").is_file())

    def test_skill_boilerplate_alias(self):
        from skills import dispatch
        with mock.patch.object(wt, "_PROJECTS", self.root):
            out = dispatch("boilerplate for quoter")
        self.assertIsInstance(out, str)
        self.assertIn("quoter", out)

    def test_git_failure_is_tolerated(self):
        with mock.patch.object(wt.subprocess, "run",
                               side_effect=FileNotFoundError("git")):
            out = wt.scaffold("plain", "nogit")
        self.assertIn("nogit", out)
        self.assertNotIn("failed", out)


if __name__ == "__main__":
    unittest.main()
