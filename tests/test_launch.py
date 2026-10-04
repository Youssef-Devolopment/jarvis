"""Universal open: resolver + URL rules. No launches, no tabs."""
import unittest

from system import launch as L


class LaunchTest(unittest.TestCase):
    def test_known_app_instant(self):
        r = L.resolve_app("notepad")
        self.assertEqual(r["status"], "found")
        self.assertTrue(L.is_instant(r["target"]))

    def test_unknown_app(self):
        r = L.resolve_app("xyznonexistent123")
        self.assertEqual(r["status"], "unknown")

    def test_fuzzy_candidates(self):
        r = L.resolve_app("notepda")
        self.assertEqual(r["status"], "candidates")
        self.assertIn("notepad", r["candidates"])

    def test_url_shortcut(self):
        self.assertEqual(L.normalize_url("youtube"),
                         "https://www.youtube.com")

    def test_url_bare_domain(self):
        self.assertEqual(L.normalize_url("example.com"),
                         "https://example.com")

    def test_url_schemes_blocked(self):
        for bad in ("file:///c:/x", "javascript:alert(1)", "data:text/plain,hi"):
            self.assertTrue(L.is_blocked_scheme(bad), bad)
            self.assertEqual(L.normalize_url(bad), "")
        self.assertFalse(L.is_blocked_scheme("https://example.com"))

    def test_open_junk_returns_empty(self):
        self.assertEqual(L.open_url("not a url at all"), "")

    def test_new_aliases_resolve(self):
        for app, exe in [("zoom", "Zoom.exe"), ("notion", "Notion.exe"),
                         ("slack", "slack.exe"),
                         ("notepad++", "notepad++.exe"),
                         ("everything", "Everything.exe"),
                         ("snipping tool", "snippingtool.exe")]:
            r = L.resolve_app(app)
            self.assertEqual(r["status"], "found", app)
            self.assertEqual(r["target"], exe, app)

    def test_obsidian_uri_when_vault_set(self):
        from unittest import mock
        fake = mock.MagicMock()
        fake.obsidian_vault = "C:\\notes\\Brain"
        with mock.patch("config.try_settings", return_value=fake):
            r = L.resolve_app("obsidian")
        self.assertEqual(r["status"], "found")
        self.assertTrue(r["target"].startswith("obsidian://open?vault="))
        self.assertIn("Brain", r["target"])

    def test_obsidian_exe_without_vault(self):
        from unittest import mock
        with mock.patch("config.try_settings", return_value=None):
            r = L.resolve_app("obsidian")
        self.assertEqual(r["target"], "obsidian.exe")


if __name__ == "__main__":
    unittest.main()
