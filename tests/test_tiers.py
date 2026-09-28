"""Autonomy tiers: dry-run gating never executes."""
import unittest

from ai.os_mode import AUTO_TOOLS, MISSION_EXCLUDED, gated_execute


class TierTest(unittest.TestCase):
    def test_auto_tools_sane(self):
        for t in ("fs_read", "read_screen", "open_url", "folder_watch"):
            self.assertIn(t, AUTO_TOOLS, t)
        for t in ("term_run", "fs_write", "win_click", "computer_run"):
            self.assertNotIn(t, AUTO_TOOLS, t)

    def test_mission_excludes_nesting(self):
        self.assertIn("computer_run", MISSION_EXCLUDED)

    def test_dry_run_executes_nothing(self):
        r = gated_execute("fs_list", {"path": "."}, dry_run=True)
        self.assertIn("dry-run", r)
        r = gated_execute("term_run", {"command": "dir"}, dry_run=True)
        self.assertIn("approval", r)

    def test_tool_schemas_cover_new_powers(self):
        from ai.tools import TOOL_SCHEMAS
        names = {t["function"]["name"] for t in TOOL_SCHEMAS}
        for want in ("read_screen", "win_click", "win_type",
                     "folder_watch", "folder_unwatch", "open_url",
                     "computer_run"):
            self.assertIn(want, names, want)


if __name__ == "__main__":
    unittest.main()
