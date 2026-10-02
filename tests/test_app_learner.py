"""Tests for the autonomous app-learning engine (no real launches)."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from system import app_learner as AL
from system import launch as L


class AppLearnerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        # fake system roots
        self.apps_root = root / "Program Files"
        (self.apps_root / "Frobnicator" / "bin").mkdir(parents=True)
        (self.apps_root / "Frobnicator" / "bin" / "frobnicator.exe").write_bytes(b"MZ")
        (self.apps_root / "SoloApp").mkdir(parents=True)
        (self.apps_root / "SoloApp" / "SoloApp.exe").write_bytes(b"MZ")
        (self.apps_root / "UninstallMe").mkdir(parents=True)
        (self.apps_root / "UninstallMe" / "unins000.exe").write_bytes(b"MZ")
        (self.apps_root / "notes.txt").write_text("not an app")
        deep = self.apps_root / "a" / "b" / "c" / "d" / "e" / "f"
        deep.mkdir(parents=True)
        (deep / "tooodeep.exe").write_bytes(b"MZ")

        # redirect stores + roots
        self._orig = (AL._SCAN_CACHE, AL._LEARNED, AL._SKILL_DIR,
                      AL._roots, list(AL._misses))
        AL._SCAN_CACHE = root / "scan.json"
        AL._LEARNED = root / "learned.json"
        AL._SKILL_DIR = root / "skills_out"
        AL._roots = lambda: [self.apps_root]
        AL._misses.clear()

        # make the real auto_generated package able to import test skills
        import skills.auto_generated as ag
        self._ag = ag
        self._ag_path = list(ag.__path__)
        ag.__path__.append(str(AL._SKILL_DIR))

        # never launch anything real in tests
        self._launch_orig = (L.is_instant, L.launch_target)
        L.is_instant = lambda p: True
        L.launch_target = lambda p: f"LAUNCHED:{p}"

    def tearDown(self):
        import sys
        # drop test-loaded generated modules so the next test re-imports
        # them fresh (and re-runs @register)
        skill_dir = str(AL._SKILL_DIR)
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", "") or ""
            if name.startswith("skills.auto_generated.") and \
                    str(Path(f).parent if f else "") == skill_dir:
                del sys.modules[name]
        for name in getattr(self, "_created_skills", []):
            try:
                from skills.registry import unregister
                unregister(name)
            except Exception:
                pass
        AL._SCAN_CACHE, AL._LEARNED, AL._SKILL_DIR, AL._roots, _ = self._orig
        AL._misses.clear()
        L.is_instant, L.launch_target = self._launch_orig
        self._ag.__path__[:] = self._ag_path
        self.tmp.cleanup()

    def _track(self, module_or_name):
        if not hasattr(self, "_created_skills"):
            self._created_skills = []
        self._created_skills.append(module_or_name)

    # ---------- scanning ----------
    def test_scan_finds_exes_skips_junk_and_depth(self):
        apps = AL.scan(force=True)
        self.assertIn("frobnicator", apps)          # nested1 level
        self.assertIn("soloapp", apps)
        self.assertNotIn("unins000", apps)          # uninstaller skipped
        self.assertNotIn("notes", apps)             # not an exe
        self.assertNotIn("tooodeep", apps)          # depth > 5

    def test_scan_uses_cache_within_ttl(self):
        AL.scan(force=True)
        # remove source: cache must still answer
        import shutil
        shutil.rmtree(self.apps_root)
        apps = AL.scan()                             # fresh cache hit
        self.assertIn("soloapp", apps)

    # ---------- find ----------
    def test_find_exact_and_fuzzy(self):
        AL.scan(force=True)
        hit = AL.find("SoloApp.exe")
        self.assertEqual(hit["name"], "SoloApp")
        self.assertEqual(hit["source"], "scan")
        fuzzy = AL.find("frob")                      # unique prefix
        self.assertEqual(fuzzy["name"], "frobnicator")
        self.assertIsNone(AL.find("definitely-not-an-app-xyz"))

    def test_learned_wins_over_scan(self):
        fake = self.apps_root / "SoloApp" / "SoloApp.exe"
        AL.ensure_skill("SoloApp", str(fake))
        self._track("app_soloapp")
        hit = AL.find("soloapp")
        self.assertEqual(hit["source"], "learned")

    # ---------- skill generation ----------
    def test_ensure_skill_writes_standard_register_pattern(self):
        fake = self.apps_root / "SoloApp" / "SoloApp.exe"
        module, created = AL.ensure_skill("SoloApp", str(fake))
        self._track(module)
        self.assertTrue(created)
        self.assertEqual(module, "app_soloapp")
        fp = AL._SKILL_DIR / "app_soloapp.py"
        src = fp.read_text(encoding="utf-8")
        self.assertIn("from skills.registry import register", src)
        self.assertIn("@register(", src)
        self.assertIn("front=True", src)
        self.assertIn(repr(str(fake)), src)          # path embedded safely
        self.assertIn("launch_learned", src)

    def test_ensure_skill_is_idempotent(self):
        fake = self.apps_root / "SoloApp" / "SoloApp.exe"
        _, first = AL.ensure_skill("SoloApp", str(fake))
        self._track("app_soloapp")
        _, second = AL.ensure_skill("SoloApp", str(fake))
        self.assertTrue(first)
        self.assertFalse(second)

    def test_ensure_skill_rejects_bad_targets(self):
        with self.assertRaises(ValueError):
            AL.ensure_skill("Ghost", str(Path(self.tmp.name) / "nope.exe"))
        txt = self.apps_root / "notes.txt"
        with self.assertRaises(ValueError):
            AL.ensure_skill("Notes", str(txt))

    def test_generated_skill_registered_at_front(self):
        from skills import all_skills, get_skill
        fake = self.apps_root / "SoloApp" / "SoloApp.exe"
        AL.ensure_skill("SoloApp", str(fake))
        self._track("app_soloapp")
        s = get_skill("app_soloapp")
        self.assertIsNotNone(s)
        self.assertTrue(s.enabled)
        # front registration -> first in dispatch order
        self.assertEqual(all_skills()[0].name, "app_soloapp")

    def test_dispatch_runs_learned_skill_without_restart(self):
        from skills import dispatch
        fake = self.apps_root / "SoloApp" / "SoloApp.exe"
        AL.ensure_skill("SoloApp", str(fake))
        self._track("app_soloapp")
        out = dispatch("open SoloApp")
        self.assertEqual(out, f"LAUNCHED:{fake}")
        out2 = dispatch("launch soloapp!")          # case + punctuation
        self.assertEqual(out2, f"LAUNCHED:{fake}")

    # ---------- learn + launch ----------
    def test_learn_and_launch_creates_skill_and_launches(self):
        res = AL.learn_and_launch("soloapp")
        self.assertIsNotNone(res)
        self._track("app_soloapp")
        self.assertTrue(res["created"])
        self.assertTrue(res["output"].startswith("LAUNCHED:"))
        self.assertTrue((AL._SKILL_DIR / "app_soloapp.py").exists())
        store = json.loads(AL._LEARNED.read_text(encoding="utf-8"))
        self.assertIn("soloapp", store["apps"])

    def test_learn_and_launch_declined(self):
        L.is_instant = lambda p: False               # gate must ask
        res = AL.learn_and_launch("soloapp", ask_fn=lambda d: False)
        self.assertIsNotNone(res)
        self._track("app_soloapp")
        self.assertTrue(res["declined"])
        self.assertTrue(res["created"])   # learned regardless

    def test_learn_and_launch_unknown_returns_none(self):
        self.assertIsNone(AL.learn_and_launch("zzz-unknown-app"))
        # negative cache: second call must NOT rescan
        AL._SCAN_CACHE.write_text(
            json.dumps({"ts": 0, "apps": {}}), encoding="utf-8")
        self.assertIsNone(AL.learn_and_launch("zzz-unknown-app"))

    # ---------- forget ----------
    def test_forget_skill_file_without_record(self):
        # fresh-clone case: skill file exists, no learned record
        fake = self.apps_root / "SoloApp" / "SoloApp.exe"
        AL.ensure_skill("SoloApp", str(fake))
        self._track("app_soloapp")
        import json as _json
        AL._LEARNED.write_text(_json.dumps({"apps": {}}), encoding="utf-8")
        self.assertTrue(AL.forget("SoloApp"))          # removes the file
        self.assertFalse((AL._SKILL_DIR / "app_soloapp.py").exists())
        from skills import get_skill
        self.assertIsNone(get_skill("app_soloapp"))

    def test_forget_reverses_everything(self):
        fake = self.apps_root / "SoloApp" / "SoloApp.exe"
        AL.ensure_skill("SoloApp", str(fake))
        self._track("app_soloapp")
        fp = AL._SKILL_DIR / "app_soloapp.py"
        self.assertTrue(fp.exists())
        from skills import get_skill
        self.assertIsNotNone(get_skill("app_soloapp"))
        self.assertTrue(AL.forget("soloapp"))
        self.assertFalse(fp.exists())
        self.assertIsNone(get_skill("app_soloapp"))
        self.assertFalse(AL.forget("soloapp"))    # already gone


if __name__ == "__main__":
    unittest.main()
