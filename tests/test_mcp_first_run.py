"""First run: a fresh install must not ship an empty MCP system.

mcp/manager.py returned `[]` when mcp_servers.json was absent, and
nothing ever created that file — it is personal and gitignored, and the
installer does not ship one. So every new user got a working MCP panel
listing zero servers, while the eight presets went undiscovered.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mcp import manager as M
from mcp import presets as P


class FirstRunSeedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="jarvis-mcp-"))
        self.cfg = self.tmp / "mcp_servers.json"
        self._p = [
            mock.patch.object(M, "_CONFIG", self.cfg),
            mock.patch.object(M, "_seeded", False),
        ]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in reversed(self._p):
            p.stop()

    def test_fresh_install_gets_servers(self):
        self.assertFalse(self.cfg.exists())
        seeded = M.ensure_seeded()
        self.assertEqual(len(seeded), 3)
        self.assertTrue(self.cfg.exists())
        self.assertEqual(len(M.all_servers()), 3)

    def test_seeding_is_idempotent(self):
        M.ensure_seeded()
        self.assertEqual(M.ensure_seeded(), [])
        self.assertEqual(len(M.all_servers()), 3)

    def test_all_servers_triggers_the_seed(self):
        """The UI reads /api/mcp and /api/market — that is the path a
        real first launch takes."""
        self.assertFalse(self.cfg.exists())
        self.assertEqual(len(M.all_servers()), 3)

    def test_existing_config_is_never_reseeded(self):
        self.cfg.write_text("[]", encoding="utf-8")
        self.assertEqual(M.ensure_seeded(), [])
        self.assertEqual(M.all_servers(), [])

    def test_existing_config_with_servers_is_untouched(self):
        original = [{"id": "keep", "name": "mine", "command": "uvx",
                     "args": ["mcp-server-time"], "enabled": True}]
        self.cfg.write_text(json.dumps(original), encoding="utf-8")
        M.ensure_seeded()
        self.assertEqual(M.all_servers(), original)

    def test_seeded_entries_have_the_shape_add_server_produces(self):
        for s in M.ensure_seeded():
            self.assertRegex(s["id"], r"^[0-9a-f]{8}$")
            self.assertTrue(s["name"])
            self.assertTrue(s["command"])
            self.assertIsInstance(s["args"], list)   # never a raw string
            self.assertIs(s["enabled"], True)

    def test_seeded_presets_need_no_key_and_no_argument(self):
        """Anything requiring a folder path, a token or an env var would
        fail on the very first start and look worse than shipping none."""
        for pid in M.FIRST_RUN_PRESETS:
            preset = P.get_preset(pid)
            self.assertIsNotNone(preset, pid)
            self.assertEqual(preset["needs"], "nothing", pid)

    def test_every_seed_id_is_a_real_preset(self):
        for pid in M.FIRST_RUN_PRESETS:
            self.assertIsNotNone(P.get_preset(pid), pid)

    def test_seed_does_not_hold_the_lock(self):
        """ensure_seeded() takes _lock itself; calling it from inside
        all_servers() must not re-enter it (Lock is not reentrant)."""
        M.ensure_seeded()
        self.assertEqual(len(M.all_servers()), 3)

    def test_rejection_reason_reaches_the_client_for_presets(self):
        from server import create_app
        client = create_app().test_client()
        r = client.post("/api/mcp/preset", json={"preset": "nope"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("nope", r.get_json()["detail"])


class PresetCatalogTests(unittest.TestCase):
    def test_catalog_is_complete_and_unique(self):
        ids = [p["id"] for p in P.list_presets()]
        self.assertGreaterEqual(len(ids), 8)
        self.assertEqual(len(ids), len(set(ids)))

    def test_unknown_preset_reports_the_id(self):
        r = P.install_preset("definitely_not_real")
        self.assertIn("error", r)
        self.assertIn("definitely_not_real", r["error"])


if __name__ == "__main__":
    unittest.main()
