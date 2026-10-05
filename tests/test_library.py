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
        self.assertEqual(len(cat["skills"]), 18)
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
        self.assertEqual(len(d["skills"]), 18)
        for s in d["skills"] + d["mcp"]:
            self.assertIsInstance(s["installed"], bool, s.get("id"))
        for m in d["mcp"]:
            self.assertIsInstance(m["running"], bool, m.get("id"))
            self.assertIsInstance(m["needs_key"], bool, m.get("id"))
            self.assertNotIn("code", m)


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
        self.assertEqual(len(d["skills"]), 18)
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


class UninstallTests(unittest.TestCase):
    def test_unknown_pack_errors(self):
        self.assertIn("error", L.uninstall_skill_pack("nope_not_real"))

    def test_uninstall_not_installed_is_idempotent(self):
        r = L.uninstall_skill_pack("word_counter")
        self.assertTrue(r["ok"])
        self.assertEqual(r["unregistered"], [])
        self.assertFalse(r["file_deleted"])

    def test_uninstall_deletes_installed_file(self):
        # simulate a real install (restores anything pre-existing)
        f = _ROOT / "plugins" / "word_counter.py"
        orig = f.read_text(encoding="utf-8") if f.exists() else None
        f.write_text("# scratch — created by test\n", encoding="utf-8")
        try:
            r = L.uninstall_skill_pack("word_counter")
            self.assertTrue(r["ok"])
            self.assertTrue(r["file_deleted"])
            self.assertFalse(f.exists())
        finally:
            if orig is not None:
                f.write_text(orig, encoding="utf-8")
            elif f.exists():
                f.unlink()

    def test_remove_unknown_mcp_errors(self):
        self.assertIn("error", L.remove_mcp_entry("nope_not_real"))

    def test_remove_mcp_stops_and_drops(self):
        fake = {"id": "ab12", "name": "time"}
        with mock.patch("mcp.manager.all_servers", return_value=[fake]), \
             mock.patch("mcp.manager.remove_server",
                        return_value=True) as rm, \
             mock.patch("mcp.runtime.stop_server",
                        return_value=True) as st:
            r = L.remove_mcp_entry("time")
        self.assertTrue(r["ok"])
        self.assertTrue(r["was_running"])
        self.assertTrue(r["removed"])
        st.assert_called_once_with("time")
        rm.assert_called_once_with("ab12")

    def test_remove_mcp_not_configured_still_ok(self):
        with mock.patch("mcp.manager.all_servers", return_value=[]), \
             mock.patch("mcp.runtime.stop_server", return_value=False):
            r = L.remove_mcp_entry("time")
        self.assertTrue(r["ok"])
        self.assertFalse(r["was_running"])
        self.assertFalse(r["removed"])


_PROBE_SRC = (
    '"""Imported test pack."""\n'
    "from skills.registry import register\n"
    "\n"
    '@register("lib_import_probe",\n'
    '          [r"^import probe$"],\n'
    '          "probe")\n'
    "def skill_probe(text, match):\n"
    '    return "probe"\n'
)


class ImportTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp()) / "user_catalog.json"
        patcher = mock.patch.object(L, "_USER_CATALOG", tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.tmp = tmp

    def test_valid_pack_imported_and_listed(self):
        r = L.import_packs({"id": "lib_probe", "name": "Probe",
                            "description": "d", "code": _PROBE_SRC})
        self.assertTrue(r["ok"])
        self.assertEqual(r["imported"], 1)
        self.assertTrue(r["results"][0]["ok"])
        self.assertTrue(self.tmp.exists())
        d = L.catalog()
        row = next((s for s in d["skills"] if s["id"] == "lib_probe"), None)
        self.assertIsNotNone(row)
        self.assertIsNone(row["code"])       # code never reaches the UI
        self.assertTrue(row.get("imported"))
        self.assertFalse(row["installed"])   # listed, not auto-installed

    def test_bad_id_rejected(self):
        r = L.import_packs({"id": "Bad-ID!", "code": _PROBE_SRC})
        self.assertEqual(r["imported"], 0)
        self.assertIn("id", r["results"][0]["error"])

    def test_bad_code_rejected(self):
        r = L.import_packs({"id": "lib_evil",
                            "code": "import os\nopen('x')\n"})
        self.assertEqual(r["imported"], 0)
        self.assertIn("rejected", r["results"][0]["error"])

    def test_duplicate_shipped_id_rejected(self):
        r = L.import_packs({"id": "word_counter", "code": _PROBE_SRC})
        self.assertEqual(r["imported"], 0)
        self.assertIn("already", r["results"][0]["error"])

    def test_list_form_and_reimport_dupe(self):
        r1 = L.import_packs({"packs": [{"id": "lib_probe",
                                        "code": _PROBE_SRC}]})
        self.assertEqual(r1["imported"], 1)
        r2 = L.import_packs({"packs": [{"id": "lib_probe",
                                        "code": _PROBE_SRC}]})
        self.assertEqual(r2["imported"], 0)
        self.assertIn("already", r2["results"][0]["error"])

    def test_uninstall_imported_drops_record(self):
        L.import_packs({"id": "lib_probe", "code": _PROBE_SRC})
        r = L.uninstall_skill_pack("lib_probe")
        self.assertTrue(r["ok"])
        ids = [e["id"] for e in L._load_user_skills()]
        self.assertNotIn("lib_probe", ids)


if __name__ == "__main__":
    unittest.main()
