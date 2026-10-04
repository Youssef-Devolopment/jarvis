"""Marketplace catalog + site unpin (read-only catalog, real data)."""
from __future__ import annotations

import unittest
from unittest import mock


class MarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_catalog_shape(self):
        r = self.__class__.client.get("/api/market")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        for key in ("skills", "pending", "plugins", "mcp_presets",
                    "mcp_servers", "sites"):
            self.assertIn(key, d, key)
        self.assertGreater(len(d["skills"]), 100)
        by_name = {s["name"]: s for s in d["skills"]}
        self.assertEqual(by_name["close_app"]["source"], "builtin")
        self.assertTrue(by_name["close_app"]["enabled"])
        for s in d["skills"]:
            self.assertIn(s["source"], ("builtin", "learned", "plugin"))
        self.assertGreater(len(d["mcp_presets"]), 0)
        self.assertIn("id", d["mcp_presets"][0])

    def test_unpin_missing_name_400(self):
        r = self.__class__.client.post("/api/sites/unpin", json={})
        self.assertEqual(r.status_code, 400)

    def test_unpin_unknown_400(self):
        with mock.patch("system.launch.unpin_site",
                        return_value="No pinned shortcut called 'zz'."):
            r = self.__class__.client.post("/api/sites/unpin",
                                           json={"name": "zz"})
        self.assertEqual(r.status_code, 400)

    def test_unpin_ok(self):
        with mock.patch("system.launch.unpin_site",
                        return_value="Removed 'yt'."):
            r = self.__class__.client.post("/api/sites/unpin",
                                           json={"name": "yt"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["ok"])


if __name__ == "__main__":
    unittest.main()
