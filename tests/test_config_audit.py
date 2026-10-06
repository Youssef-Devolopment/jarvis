"""config.audit_settings — static config-drift warnings (never raises)."""
from __future__ import annotations

import dataclasses
import unittest

from config import Settings, audit_settings


def _mk(**over) -> Settings:
    """Settings with every field None, then explicit overrides."""
    vals = {f.name: None for f in dataclasses.fields(Settings)}
    vals.update(over)
    return Settings(**vals)


def _clean(**over) -> Settings:
    """A known-good configuration; pass overrides to break one thing."""
    base = dict(
        api_key="sk-realkey0123456789",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
        port=5001,
        temperature=0.2,
        max_tokens=400,
        host="127.0.0.1",
        log_level="INFO",
        debug=False,
        voice_name="en-GB-Ryan",
        browser_engine="duckduckgo",
        obsidian_vault="",
    )
    base.update(over)
    return _mk(**base)


class AuditTests(unittest.TestCase):
    def test_clean_config_has_no_warnings(self):
        self.assertEqual(audit_settings(_clean()), [])

    def test_port_out_of_range(self):
        warns = audit_settings(_clean(port=70000))
        self.assertTrue(any("PORT" in w for w in warns))

    def test_temperature_out_of_range(self):
        warns = audit_settings(_clean(temperature=7.0))
        self.assertTrue(any("TEMPERATURE" in w for w in warns))

    def test_max_tokens_out_of_range(self):
        warns = audit_settings(_clean(max_tokens=0))
        self.assertTrue(any("MAX_TOKENS" in w for w in warns))

    def test_non_http_base_url(self):
        warns = audit_settings(_clean(base_url="ftp://nowhere"))
        self.assertTrue(any("http(s) URL" in w for w in warns))

    def test_gpt_model_on_deepseek_url(self):
        warns = audit_settings(_clean(model="gpt-4o-mini"))
        self.assertTrue(any("pairing" in w for w in warns))

    def test_deepseek_model_on_foreign_url_is_fine(self):
        # Proxies/rebadged providers are documented ("any OpenAI-compatible
        # base URL") — a deepseek-* model on a foreign URL is legitimate.
        warns = audit_settings(_clean(base_url="https://api.other.ai/v1"))
        self.assertFalse(any("pairing" in w for w in warns))

    def test_empty_voice_name(self):
        warns = audit_settings(_clean(voice_name="  "))
        self.assertTrue(any("VOICE_NAME" in w for w in warns))

    def test_unknown_browser_engine(self):
        warns = audit_settings(_clean(browser_engine="netscape"))
        self.assertTrue(any("BROWSER_ENGINE" in w for w in warns))

    def test_missing_obsidian_vault(self):
        warns = audit_settings(
            _clean(obsidian_vault="C:\\definitely\\not\\a\\folder\\xyz"))
        self.assertTrue(any("OBSIDIAN_VAULT" in w for w in warns))

    def test_invalid_log_level(self):
        warns = audit_settings(_clean(log_level="LOUD"))
        self.assertTrue(any("LOG_LEVEL" in w for w in warns))

    def test_debug_on_non_loopback_host(self):
        warns = audit_settings(_clean(debug=True, host="0.0.0.0"))
        self.assertTrue(any("FLASK_DEBUG" in w for w in warns))

    def test_skills_only_mode_does_not_spam(self):
        # No key: placeholder/URL mismatches are meaningless — stay quiet.
        warns = audit_settings(_clean(api_key=None, base_url="weird",
                                      model="deepseek-chat"))
        self.assertEqual(warns, [])

    def test_never_raises_on_garbage(self):
        warns = audit_settings(_mk(temperature="hot", max_tokens="lots",
                                   port="wide"))
        self.assertGreaterEqual(len(warns), 3)


if __name__ == "__main__":
    unittest.main()
