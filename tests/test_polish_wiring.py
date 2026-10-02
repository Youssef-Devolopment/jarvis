"""Wiring tests: persistent `remember` skill + durable auto-approve gate.

Covers the v1.0.0 polish batch:
  - remember -> core SQLite facts (recall + facts_block injection)
  - auto_approve_skills pref -> real approval pipeline bypass/gate
  - skill replies reflect the persisted state
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import memory.prefs as prefs
import memory.store as st
from skills import auto_generator as ag

_REAL_DB = st._DB_PATH
_REAL_PREFDB = prefs._DB

_GATE_CODE = (
    "from skills.registry import register\n"
    "\n"
    '@register("zz_gate_probe",\n'
    '          [r"^ping the gate$"],\n'
    '          "gate probe candidate")\n'
    "def zz_gate_probe(text, match):\n"
    '    return "pong"\n'
)


class RememberSkillTests(unittest.TestCase):
    """The remember skill must really persist (facts table)."""

    def setUp(self):
        st._DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
        st._conn = None

    def tearDown(self):
        st._DB_PATH = _REAL_DB
        st._conn = None

    def test_dispatch_remember_persists_fact_with_timestamp(self):
        from skills import dispatch
        out = dispatch("remember that my favorite editor is Neovim")
        self.assertTrue(out)
        self.assertIn("memory", out.lower())
        hits = st.recall("neovim")
        self.assertEqual(len(hits), 1)
        self.assertIn("Neovim", hits[0]["fact"])
        self.assertTrue(hits[0].get("created_at"))       # timestamped
        self.assertEqual(hits[0].get("category"), "general")
        # the LLM system prompt gets it (ai/client.py uses facts_block)
        self.assertIn("Neovim", st.facts_block(limit=12))

    def test_dispatch_remember_dedupes(self):
        from skills import dispatch
        dispatch("remember that my favorite editor is Neovim")
        dispatch("remember that my favorite editor is Neovim")
        self.assertEqual(len(st.recall("neovim")), 1)

    def test_empty_fact_falls_through_to_other_skills(self):
        from skills import get_skill
        sk = get_skill("remember")
        self.assertIsNotNone(sk)
        m = sk.match("remember that   ---   ")
        self.assertIsNotNone(m)
        # nothing survives the strip -> skill declines (returns None),
        # letting other skills / the LLM handle it
        self.assertIsNone(sk.run("remember that   ---   ", m))
        self.assertEqual(len(st.recall("")), 0)


class AutoApprovePrefTests(unittest.TestCase):
    """The pref lives in the real config store and drives the gate."""

    def setUp(self):
        prefs._DB = Path(tempfile.mkdtemp()) / "prefs.db"
        self.tmp = Path(tempfile.mkdtemp())
        self._orig = (ag._LOG_DIR, ag._PENDING_FILE, ag._AUTO_DIR,
                      ag._AUDIT, dict(ag._PENDING))
        (self.tmp / "cand").mkdir()
        (self.tmp / "autogen").mkdir()
        ag._LOG_DIR = self.tmp / "cand"
        ag._PENDING_FILE = self.tmp / "pending.json"
        ag._AUTO_DIR = self.tmp / "autogen"
        ag._AUDIT = self.tmp / "audit.log"
        ag._PENDING.clear()
        import skills.auto_generated as pkg
        self._pkg = pkg
        self._pkg_path = list(pkg.__path__)
        pkg.__path__.append(str(ag._AUTO_DIR))

    def tearDown(self):
        # unregister anything this test registered + drop loaded modules
        for name in list({p["name"] for p in ag.list_pending()} |
                         {"zz_gate_probe"}):
            try:
                from skills.registry import unregister
                unregister(name)
            except Exception:
                pass
        for name, mod in list(sys.modules.items()):
            f = getattr(mod, "__file__", "") or ""
            if name.startswith("skills.auto_generated.") and \
                    str(Path(f).parent if f else "") == str(ag._AUTO_DIR):
                del sys.modules[name]
        (ag._LOG_DIR, ag._PENDING_FILE, ag._AUTO_DIR, ag._AUDIT,
         pend) = self._orig
        ag._PENDING.clear()
        ag._PENDING.update(pend)
        self._pkg.__path__[:] = self._pkg_path
        prefs._DB = _REAL_PREFDB

    # ---------- pref storage ----------
    def test_pref_defaults_on_and_is_durable(self):
        self.assertTrue(ag.auto_approve_enabled())       # fresh DB default
        self.assertTrue(ag.set_auto_approve_enabled(False))
        self.assertFalse(prefs.get_pref("auto_approve_skills", True))
        # durability: a brand-new connection reads the same value back
        self.assertFalse(ag.auto_approve_enabled())

    # ---------- the gate ----------
    def test_off_stages_candidate_and_blocks_registration(self):
        ag.set_auto_approve_enabled(False)
        res = ag.stage_candidate(_GATE_CODE, "ping the gate")
        self.assertFalse(res["auto_approved"])
        self.assertTrue(res["test_ok"])
        self.assertIn("zz_gate_probe", [p["name"] for p in ag.list_pending()])
        from skills import get_skill
        self.assertIsNone(get_skill("zz_gate_probe"))     # NOT live
        self.assertFalse((ag._AUTO_DIR / "zz_gate_probe.py").exists())

    def test_on_auto_approves_only_after_passing_test(self):
        self.assertTrue(ag.auto_approve_enabled())        # default ON
        res = ag.stage_candidate(_GATE_CODE, "ping the gate")
        self.assertTrue(res["auto_approved"])
        self.assertEqual(ag.list_pending(), [])           # queue drained
        from skills import get_skill
        self.assertIsNotNone(get_skill("zz_gate_probe"))  # live now
        self.assertTrue((ag._AUTO_DIR / "zz_gate_probe.py").exists())

    def test_failing_test_never_bypasses_the_human(self):
        # pref ON, but the isolation test fails (pattern mismatch)
        res = ag.stage_candidate(_GATE_CODE, "this will not match")
        self.assertFalse(res["test_ok"])
        self.assertFalse(res["auto_approved"])
        self.assertIn("zz_gate_probe", [p["name"] for p in ag.list_pending()])
        from skills import get_skill
        self.assertIsNone(get_skill("zz_gate_probe"))

    def test_reapprove_after_change_registers_once(self):
        from skills import all_skills
        ag.set_auto_approve_enabled(False)
        ag.stage_candidate(_GATE_CODE, "ping the gate")
        self.assertTrue(ag.approve_skill("zz_gate_probe")["ok"])
        # candidate changed -> staged again -> approved again
        changed = _GATE_CODE.replace("gate probe candidate",
                                     "gate probe candidate v2")
        ag.stage_candidate(changed, "ping the gate")
        self.assertTrue(ag.approve_skill("zz_gate_probe")["ok"])
        twins = [s for s in all_skills() if s.name == "zz_gate_probe"]
        self.assertEqual(len(twins), 1)                   # never duplicated
        self.assertIn("v2", twins[0].description)

    def test_drop_pending_cleans_stale_entries(self):
        ag.set_auto_approve_enabled(False)
        ag.stage_candidate(_GATE_CODE, "ping the gate")
        self.assertTrue(ag.drop_pending("zz_gate_probe"))
        self.assertEqual(ag.list_pending(), [])
        self.assertFalse(ag.drop_pending("zz_gate_probe"))  # idempotent

    # ---------- validation rails ----------
    def test_llm_candidates_cannot_import_system(self):
        bad = ("from skills.registry import register\n"
               "import system\n"
               "@register(\"zz_bad\", [r\"^bad$\"], \"x\")\n"
               "def zz_bad(t, m):\n    return \"x\"\n")
        with self.assertRaises(ValueError):
            ag._validate(bad)                            # LLM draft
        ag._validate(bad, trusted=True)                  # app template OK

    # ---------- the toggle skill reflects real state ----------
    def _run_skill(self, text):
        from skills import get_skill
        sk = get_skill("auto_approve_skills")
        self.assertIsNotNone(sk)
        m = sk.match(text)
        self.assertIsNotNone(m, f"pattern must match: {text!r}")
        return sk.run(text, m)

    def test_toggle_skill_reports_and_changes_state(self):
        self.assertTrue(ag.set_auto_approve_enabled(False))
        out = self._run_skill("auto approve skills")
        self.assertIn("OFF", out)
        out = self._run_skill("enable auto approve skills")
        self.assertIn("ON", out)
        self.assertTrue(prefs.get_pref("auto_approve_skills", True))
        out = self._run_skill("disable auto approve skills")
        self.assertIn("OFF", out)
        self.assertFalse(prefs.get_pref("auto_approve_skills", True))
        # reply mentions the actual gate behavior
        self.assertIn("approval", out.lower())


if __name__ == "__main__":
    unittest.main()
