"""config.audit_settings — static config-drift warnings (never raises)."""
from __future__ import annotations

import dataclasses
import os
import unittest
from unittest import mock

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
    def setUp(self):
        # Tavily is read from the environment and MCP servers come
        # from the (personal, gitignored) mcp_servers.json — keep
        # these tests hermetic regardless of the machine.
        self._tav = os.environ.pop("TAVILY_API_KEY", None)
        self._mcp = mock.patch("mcp.manager.all_servers", return_value=[])
        self._mcp.start()

    def tearDown(self):
        self._mcp.stop()
        if self._tav is not None:
            os.environ["TAVILY_API_KEY"] = self._tav

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

    def test_groq_key_with_wrong_prefix_warns(self):
        warns = audit_settings(_clean(groq_api_key="not-a-groq-key"))
        self.assertTrue(any("GROQ_API_KEY" in w for w in warns))

    def test_groq_key_with_gsk_prefix_is_silent(self):
        warns = audit_settings(_clean(groq_api_key="gsk_test123456"))
        self.assertFalse(any("GROQ_API_KEY" in w for w in warns))

    def test_tavily_key_with_wrong_prefix_warns(self):
        with mock.patch.dict(os.environ, {"TAVILY_API_KEY": "oops"}):
            warns = audit_settings(_clean())
        self.assertTrue(any("TAVILY_API_KEY" in w for w in warns))

    def test_tavily_key_with_tvly_prefix_is_silent(self):
        with mock.patch.dict(os.environ,
                             {"TAVILY_API_KEY": "tvly-test-12345"}):
            warns = audit_settings(_clean())
        self.assertFalse(any("TAVILY_API_KEY" in w for w in warns))

    def test_groq_template_placeholder_warns(self):
        # Passes the gsk_ prefix check but can never work.
        warns = audit_settings(_clean(groq_api_key="gsk_your-key-here"))
        self.assertTrue(any("GROQ_API_KEY" in w and "placeholder" in w
                            for w in warns), warns)

    def test_tavily_template_placeholder_warns(self):
        with mock.patch.dict(os.environ,
                             {"TAVILY_API_KEY": "tvly-paste-me"}):
            warns = audit_settings(_clean())
        self.assertTrue(any("TAVILY_API_KEY" in w and "placeholder" in w
                            for w in warns), warns)

    def test_mcp_servers_without_npx_warn_with_install_hint(self):
        servers = [{"enabled": True, "command": "npx", "name": "fs"},
                   {"enabled": False, "command": "npx", "name": "off"}]
        with mock.patch("mcp.manager.all_servers", return_value=servers), \
             mock.patch("shutil.which", return_value=None):
            warns = audit_settings(_clean())
        hits = [w for w in warns if "npx" in w]
        self.assertTrue(hits, warns)
        self.assertIn("1 MCP server(s)", hits[0])       # disabled ones skip
        self.assertIn("nodejs.org", hits[0])            # actionable hint

    def test_mcp_npx_present_is_silent(self):
        servers = [{"enabled": True, "command": "npx", "name": "fs"}]
        with mock.patch("mcp.manager.all_servers", return_value=servers), \
             mock.patch("shutil.which",
                        return_value="C:\\nodejs\\npx.cmd"):
            warns = audit_settings(_clean())
        self.assertFalse(any("npx" in w for w in warns), warns)

    def test_non_npx_servers_ignore_missing_npx(self):
        servers = [{"enabled": True, "command": "python.exe",
                    "name": "local"}]
        with mock.patch("mcp.manager.all_servers", return_value=servers), \
             mock.patch("shutil.which", return_value=None):
            warns = audit_settings(_clean())
        self.assertFalse(any("npx" in w for w in warns), warns)

    def test_no_mcp_servers_is_silent_even_without_npx(self):
        with mock.patch("mcp.manager.all_servers", return_value=[]), \
             mock.patch("shutil.which", return_value=None):
            warns = audit_settings(_clean())
        self.assertFalse(any("npx" in w for w in warns), warns)

    def test_unset_optional_keys_stay_silent(self):
        # _clean() leaves groq empty and setUp dropped TAVILY — no noise.
        warns = audit_settings(_clean(groq_api_key=""))
        self.assertEqual(warns, [])

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
