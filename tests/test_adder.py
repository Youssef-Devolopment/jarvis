"""Universal add: pin/remove sites, MCP presets, app learning,
skill drafts — routing only, backends mocked or temp-pathed."""
from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from system import adder
from system import launch as L
from skills.add_anything import ADD_PATTERNS


def _tmp():
    return Path(tempfile.mkdtemp()) / "sites.json"


class SitePinTests(unittest.TestCase):
    def test_pin_and_resolve(self):
        p = _tmp()
        self.assertIn("Pinned 'yt'", L.pin_site("yt", "https://youtube.com", p))
        self.assertEqual(L.custom_sites(p)["yt"], "https://youtube.com")
        with mock.patch.object(L, "custom_sites",
                               return_value={"yt": "https://youtube.com"}):
            self.assertEqual(L.normalize_url("yt"), "https://youtube.com")
            self.assertEqual(L.normalize_url("YT"), "https://youtube.com")

    def test_pin_bare_domain_gets_scheme(self):
        p = _tmp()
        self.assertIn("Pinned", L.pin_site("gh", "github.com", p))
        self.assertTrue(L.custom_sites(p)["gh"].startswith("https://"))

    def test_pin_rejects_dangerous_and_garbage(self):
        p = _tmp()
        self.assertIn("Refused", L.pin_site("x", "javascript:alert(1)", p))
        self.assertIn("doesn't look like",
                      L.pin_site("x", "notaurl", p))
        self.assertEqual(L.custom_sites(p), {})

    def test_unpin(self):
        p = _tmp()
        L.pin_site("yt", "https://youtube.com", p)
        self.assertIn("Removed", L.unpin_site("yt", p))
        self.assertIn("No pinned", L.unpin_site("yt", p))

    def test_corrupt_store_reads_empty(self):
        p = _tmp()
        p.write_text("not json{{", encoding="utf-8")
        self.assertEqual(L.custom_sites(p), {})


class EngineTests(unittest.TestCase):
    def test_not_an_add_command(self):
        for t in ["what time is it", "open notepad",
                  "add mcp server foo command npx x"]:
            self.assertIsNone(adder.add(t), t)

    def test_stem_of_url(self):
        self.assertEqual(adder._stem_of_url("https://github.com/x"), "github")
        self.assertEqual(adder._stem_of_url("https://www.youtube.com/"), "youtube")
        self.assertEqual(adder._stem_of_url("https://mail.google.com/"), "mail")

    def test_add_domain_as_site(self):
        with mock.patch.object(L, "pin_site",
                               return_value="Pinned.") as pin:
            out = adder.add("add github.com as a site")
            self.assertEqual(out, "Pinned.")
            pin.assert_called_once()
            args = pin.call_args[0]
            self.assertEqual(args[0], "github")
            self.assertTrue(args[1].startswith("https://"))

    def test_add_bare_name_gets_guidance(self):
        out = adder.add("add youtube as a site")
        self.assertIn("remember <url> as youtube", out)

    def test_remember_url_as_name(self):
        with mock.patch.object(L, "pin_site",
                               return_value="Pinned.") as pin:
            adder.add("remember https://example.com/docs as docs")
            pin.assert_called_with("docs", "https://example.com/docs")

    def test_remove_site(self):
        with mock.patch.object(L, "unpin_site",
                               return_value="Removed.") as un:
            self.assertEqual(adder.add("forget site yt"), "Removed.")
            un.assert_called_with("yt")

    def test_mcp_unknown_preset_lists_available(self):
        fake = mock.MagicMock()
        fake.list_presets.return_value = [{"id": "filesystem"},
                                          {"id": "fetch"}]
        with mock.patch.dict("sys.modules", {"mcp.presets": fake}):
            out = adder.add("add mcp nosuch")
        self.assertIn("Unknown preset", out)
        self.assertIn("filesystem", out)

    def test_mcp_preset_install(self):
        fake = mock.MagicMock()
        fake.list_presets.return_value = [{"id": "fetch"}]
        fake.install_preset.return_value = {"ok": True, "needs": "npx"}
        with mock.patch.dict("sys.modules", {"mcp.presets": fake}):
            out = adder.add("install mcp fetch")
        self.assertIn("installed", out)
        fake.install_preset.assert_called_with("fetch")

    def test_mcp_server_add(self):
        mgr = mock.MagicMock()
        mgr.add_server.return_value = {"ok": True}
        with mock.patch("mcp.manager", mgr):
            out = adder.add("add mcp server named foo running npx -y bar")
        self.assertIn("added", out)
        mgr.add_server.assert_called_with("foo", "npx", "-y bar")

    def test_app_learn_found_and_live(self):
        al = mock.MagicMock()
        al.find.return_value = {"name": "Frob", "path": "C:\\frob.exe"}
        al.ensure_skill.return_value = ("app_frob", True)
        reg = mock.MagicMock()
        reg.get_skill.return_value = object()
        with mock.patch.dict("sys.modules",
                             {"system.app_learner": al,
                              "skills.registry": reg}), \
             mock.patch("system.app_learner", al, create=True), \
             mock.patch("skills.registry", reg):
            out = adder.add("add frob as an app")
        self.assertIn("say 'open Frob'", out)

    def test_app_learn_miss(self):
        al = mock.MagicMock()
        al.find.return_value = None
        al.scan.return_value = {}
        with mock.patch.dict("sys.modules", {"system.app_learner": al}), \
             mock.patch("system.app_learner", al, create=True):
            out = adder.add("add zzz-nope as an app")
        self.assertIn("Could not find", out)

    def test_skill_draft(self):
        ag = mock.MagicMock()
        ag.propose_skill.return_value = {"name": "zz_x"}
        ag.approval_prompt.return_value = "APPROVE-ME"
        with mock.patch.dict("sys.modules",
                             {"skills.auto_generator": ag}), \
             mock.patch("skills.auto_generator", ag, create=True):
            self.assertEqual(adder.add("add a skill that pings"), "APPROVE-ME")

    def test_skill_patterns_match(self):
        for good in ["add github.com as a site",
                     "remember https://x.y as why",
                     "forget site old",
                     "add mcp fetch",
                     "add frob as an app",
                     "add a skill that pings"]:
            self.assertTrue(any(re.match(p, good, re.IGNORECASE)
                                for p in ADD_PATTERNS), good)


if __name__ == "__main__":
    unittest.main()
