"""Error reasons must reach the client.

errors.py used to put the caller's message in Exception.args (server
log only) and send the class-level public_message, so every failure —
adding a skill, a plugin, an MCP server — came back as `detail: ""` /
`error: "Invalid request."`. The UI rendered "✗ Invalid request." no
matter what actually went wrong, which is why all three add flows felt
completely broken.
"""
from __future__ import annotations

import unittest

from errors import ValidationError


class ReasonStoredTests(unittest.TestCase):
    def test_positional_message_becomes_detail(self):
        self.assertEqual(ValidationError("Missing 'name'.").detail,
                         "Missing 'name'.")

    def test_explicit_detail_still_wins(self):
        e = ValidationError("Could not write .env.", detail="disk full")
        self.assertEqual(e.detail, "disk full")

    def test_no_message_means_no_detail(self):
        self.assertEqual(ValidationError().detail, "")

    def test_generic_public_message_unchanged(self):
        # The headline stays the stable, machine-independent string.
        self.assertEqual(ValidationError.public_message, "Invalid request.")
        self.assertEqual(ValidationError("Missing 'name'.").public_message,
                         "Invalid request.")

    def test_message_is_still_available_to_the_logger(self):
        e = ValidationError("Unknown mood: sleepy")
        self.assertEqual(str(e), "Unknown mood: sleepy")

    def test_every_error_class_keeps_its_status_code(self):
        self.assertEqual(ValidationError("x").status_code, 400)
        from errors import AIError, ConfigError, SkillError
        self.assertEqual(AIError("x").status_code, 502)
        self.assertEqual(ConfigError("x").status_code, 500)
        self.assertEqual(SkillError("x").status_code, 500)


class HttpReasonTests(unittest.TestCase):
    """The three add flows, end to end, through a real Flask client."""

    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def _reason(self, path, payload):
        r = self.client.post(path, json=payload)
        self.assertEqual(r.status_code, 400, r.get_data(as_text=True))
        data = r.get_json()
        self.assertEqual(data["type"], "ValidationError")
        return data

    def test_add_skill_missing_name(self):
        d = self._reason("/api/skill", {})
        self.assertEqual(d["detail"], "Missing 'name'.")

    def test_add_skill_unknown_name(self):
        d = self._reason("/api/skill", {"name": "nope_not_real"})
        self.assertIn("nope_not_real", d["detail"])

    def test_add_mcp_server_missing_fields(self):
        d = self._reason("/api/mcp", {})
        self.assertTrue(d["detail"])

    def test_add_mcp_preset_unknown_id(self):
        d = self._reason("/api/mcp/preset", {"preset": "not_a_preset"})
        self.assertIn("not_a_preset", d["detail"])

    def test_add_plugin_missing_code(self):
        d = self._reason("/api/plugins/install", {"name": "z"})
        self.assertTrue(d["detail"])

    def test_rejected_plugin_explains_which_rule_fired(self):
        """The case the README promises: 'violations are rejected with
        a reason'."""
        code = ("import subprocess\n"
                "from skills.registry import register\n"
                '@register("probe_sub", [r"^probe sub$"], "d")\n'
                "def s(t, m):\n    return 1")
        d = self._reason("/api/plugins/install",
                         {"name": "t_sub", "code": code})
        self.assertIn("blocked import: subprocess", d["detail"])

    def test_rejected_plugin_without_register_explains_itself(self):
        code = "def s(t, m):\n    return 1"
        d = self._reason("/api/plugins/install",
                         {"name": "t_noreg", "code": code})
        self.assertIn("@register", d["detail"])

    def test_reason_never_falls_back_to_the_generic_string(self):
        """The whole point: 'Invalid request.' alone is useless."""
        d = self._reason("/api/mcp/preset", {"preset": "nope"})
        self.assertNotEqual(d["detail"], "")
        self.assertNotEqual(d["detail"], ValidationError.public_message)

    def test_error_field_keeps_the_stable_headline(self):
        d = self._reason("/api/skill", {})
        self.assertEqual(d["error"], "Invalid request.")


if __name__ == "__main__":
    unittest.main()
