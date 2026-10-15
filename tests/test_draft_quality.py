"""v1.29.0 — drafter quality bar (principle 6).

Seen live: an auto-drafted skill passed isolation and auto-approved
while telling the user "no file-writing tool exists" and "I only
have read-only skills available" — 31 tools exist. Now capability
lies park for a human verdict (never auto-approve); honest drafts
and explicit manual approvals are unaffected.
"""
import sys
import tempfile
import unittest
from pathlib import Path

import memory.prefs as prefs
from skills import auto_generator as ag

_REAL_PREFDB = prefs._DB

_LIE_CODE = (
    "from skills.registry import register\n"
    "\n"
    '@register("zz_claim_probe",\n'
    '          [r"^write a note$"],\n'
    '          "Reports that no file-writing tool exists")\n'
    "def zz_claim_probe(text, match):\n"
    '    return "I only have read-only skills available."\n'
)

_OK_CODE = (
    "from skills.registry import register\n"
    "\n"
    '@register("zz_honest_probe",\n'
    '          [r"^ping quality$"],\n'
    '          "honest probe candidate")\n'
    "def zz_honest_probe(text, match):\n"
    '    return "pong"\n'
)

_LIMIT_CODE = (
    "from skills.registry import register\n"
    "\n"
    '@register("zz_limit_probe",\n'
    '          [r"^do the impossible$"],\n'
    '          "declines honestly")\n'
    "def zz_limit_probe(text, match):\n"
    '    return "I can\'t do that, sir."\n'
)


class DraftQualityTests(unittest.TestCase):
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
        for name in list({p["name"] for p in ag.list_pending()} |
                         {"zz_claim_probe", "zz_honest_probe",
                          "zz_limit_probe"}):
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

    def test_capability_lie_parks_for_human_verdict(self):
        self.assertTrue(ag.auto_approve_enabled())  # pref ON, fresh DB
        res = ag.stage_candidate(_LIE_CODE, "write a note")
        self.assertFalse(res["test_ok"])
        self.assertIn("capability-claim rejected", res["test_output"])
        self.assertFalse(res["auto_approved"])       # never auto
        self.assertIn("zz_claim_probe",
                      [p["name"] for p in ag.list_pending()])
        from skills import get_skill
        self.assertIsNone(get_skill("zz_claim_probe"))  # NOT live

    def test_honest_draft_still_auto_approves(self):
        res = ag.stage_candidate(_OK_CODE, "ping quality")
        self.assertTrue(res["test_ok"])
        self.assertTrue(res["auto_approved"])
        from skills import get_skill
        self.assertIsNotNone(get_skill("zz_honest_probe"))

    def test_honest_self_limit_passes_the_bar(self):
        ag.set_auto_approve_enabled(False)
        res = ag.stage_candidate(_LIMIT_CODE, "do the impossible")
        self.assertTrue(res["test_ok"], res["test_output"])
        self.assertIsNone(ag._check_claims(
            _LIMIT_CODE, {"description": "declines honestly"}))

    def test_description_only_lie_caught(self):
        hit = ag._check_claims(
            _OK_CODE, {"description": "No write tool available here"})
        self.assertIsNotNone(hit)

    def test_manual_approval_still_possible_after_claims_hit(self):
        ag.set_auto_approve_enabled(False)
        res = ag.stage_candidate(_LIE_CODE, "write a note")
        self.assertFalse(res["test_ok"])
        # the human read the warning and overrides explicitly
        self.assertTrue(ag.approve_skill("zz_claim_probe")["ok"])
        from skills import get_skill
        self.assertIsNotNone(get_skill("zz_claim_probe"))

    def test_generation_prompt_teaches_honesty(self):
        self.assertIn("never claim", ag._GENERATION_PROMPT.lower())
        self.assertIn("does not exist", ag._GENERATION_PROMPT)


if __name__ == "__main__":
    unittest.main()
