"""One-click library: catalog validity, install/add flows, API."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from system import library as L

_ROOT = Path(__file__).resolve().parent.parent


class CatalogTests(unittest.TestCase):
    def test_catalog_loads_unique_ids(self):
        cat = L.load_catalog()
        self.assertEqual(len(cat["skills"]), 13)
        self.assertGreaterEqual(len(cat["mcp"]), 10)
        ids = [e["id"] for e in cat["skills"]]
        self.assertEqual(len(ids), len(set(ids)))
        mids = [e["id"] for e in cat["mcp"]]
        self.assertEqual(len(mids), len(set(mids)))

    def test_every_pack_passes_validator(self):
        from skills.auto_generator import _validate
        for e in L.load_catalog()["skills"]:
            src = (_ROOT / "library" / "skills" / e["file"]) \
                .read_text(encoding="utf-8")
            r = _validate(src)
            self.assertNotIn("error", r, f"{e['id']}: {r.get('error')}")

    def test_pack_skill_names_format_and_unique(self):
        seen = set()
        for e in L.load_catalog()["skills"]:
            names = L._pack_skill_names(e)
            self.assertTrue(names, e["id"])
            for n in names:
                self.assertRegex(n, r"^[a-z][a-z0-9_]{0,29}$")
                self.assertNotIn(n, seen, f"duplicate skill name {n}")
                seen.add(n)

    def test_mcp_entries_shape(self):
        for e in L.load_catalog()["mcp"]:
            self.assertTrue(e.get("name"), e.get("id"))
            self.assertTrue(e.get("command"), e.get("id"))
            self.assertIsInstance(e.get("args") or [], list, e["id"])
            self.assertIn("auto_start", e, e["id"])

    def test_placeholders_expand(self):
        out = L._expand(["{HOME}/x", "{DOCUMENTS}", "plain"])
        self.assertNotIn("{HOME}", out[0])
        self.assertTrue(out[0].endswith("/x"))
        self.assertNotIn("{", out[1])
        self.assertEqual(out[2], "plain")

    def test_catalog_flags_are_bools(self):
        d = L.catalog()
        self.assertEqual(len(d["skills"]), 13)
        for s in d["skills"] + d["mcp"]:
            self.assertIsInstance(s["installed"], bool, s.get("id"))


class InstallTests(unittest.TestCase):
    def test_unknown_pack_errors(self):
        r = L.install_skill_pack("nope_not_real")
        self.assertIn("error", r)

    def test_install_pack_calls_plugin_loader(self):
        with mock.patch("plugins.install_plugin",
                        return_value={"ok": True,
                                      "skill": "word_counter"}) as m:
            r = L.install_skill_pack("word_counter")
        self.assertTrue(r["ok"])
        self.assertEqual(r["skill"], "word_counter")
        name, code = m.call_args[0]
        self.assertEqual(name, "word_counter")
        self.assertIn("@register", code)

    def test_install_propagates_plugin_error(self):
        with mock.patch("plugins.install_plugin",
                        return_value={"error": "bad code"}):
            r = L.install_skill_pack("rot13")
        self.assertEqual(r["error"], "bad code")


class McpAddTests(unittest.TestCase):
    def test_unknown_mcp_errors(self):
        r = L.add_mcp_entry("nope_not_real")
        self.assertIn("error", r)

    def test_add_and_start(self):
        fake = {"id": "ab12", "name": "memory", "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "enabled": True}
        with mock.patch("mcp.manager.all_servers", return_value=[]), \
             mock.patch("mcp.manager.add_server",
                        return_value=fake) as add, \
             mock.patch("mcp.runtime.start_server",
                        return_value=True) as st:
            r = L.add_mcp_entry("memory")
        self.assertTrue(r["ok"])
        self.assertTrue(r["added"])
        self.assertTrue(r["started"])
        add.assert_called_once()
        st.assert_called_once_with("memory")

    def test_already_present_not_readded(self):
        fake = {"id": "x", "name": "memory"}
        with mock.patch("mcp.manager.all_servers", return_value=[fake]), \
             mock.patch("mcp.manager.add_server") as add, \
             mock.patch("mcp.runtime.start_server", return_value=True):
            r = L.add_mcp_entry("memory")
        self.assertFalse(r["added"])
        add.assert_not_called()

    def test_entry_needing_key_skips_start(self):
        # brave-search ships an empty env value -> must NOT auto-start
        # and must tell the user to set the key first.
        fake = {"id": "zz", "name": "brave-search"}
        with mock.patch("mcp.manager.all_servers", return_value=[]), \
             mock.patch("mcp.manager.add_server", return_value=fake), \
             mock.patch("mcp.runtime.start_server") as st, \
             mock.patch("mcp.manager._load", return_value=[]), \
             mock.patch("mcp.manager._save"):
            r = L.add_mcp_entry("brave-search")
        self.assertTrue(r["ok"])
        self.assertTrue(r["needs_key"])
        self.assertIsNone(r["started"])
        self.assertIn("API key", r["note"])
        st.assert_not_called()


class LibraryApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_get_library_shape(self):
        r = self.__class__.client.get("/api/library")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertEqual(len(d["skills"]), 13)
        self.assertGreaterEqual(len(d["mcp"]), 10)
        self.assertIn("installed", d["skills"][0])
        self.assertIn("installed", d["mcp"][0])

    def test_post_skill_missing_id_400(self):
        r = self.__class__.client.post("/api/library/skill", json={})
        self.assertEqual(r.status_code, 400)

    def test_post_mcp_missing_id_400(self):
        r = self.__class__.client.post("/api/library/mcp", json={})
        self.assertEqual(r.status_code, 400)

    def test_post_skill_install_mocked(self):
        with mock.patch("plugins.install_plugin",
                        return_value={"ok": True, "skill": "coin_flip"}):
            r = self.__class__.client.post("/api/library/skill",
                                           json={"id": "coin_flip"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])

    def test_post_mcp_unknown_400(self):
        r = self.__class__.client.post("/api/library/mcp",
                                       json={"id": "not-a-server"})
        self.assertEqual(r.status_code, 400)


if __name__ == "__main__":
    unittest.main()
