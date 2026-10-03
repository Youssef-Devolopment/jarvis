"""No-key (skills-only) mode: the server must boot and serve local
skills without DEEPSEEK_API_KEY; only LLM paths degrade, with a
clear setup hint instead of a crash or a bare 500.
"""
from __future__ import annotations

import json
import os
import unittest

import config
from config import Settings
from errors import ConfigError

_PLACEHOLDER = "sk-paste-test-key"


class _NoKeyEnv:
    """Swap DEEPSEEK_API_KEY + drop the settings and AI-client caches,
    then restore. (ai/client.py caches clients globally, so earlier
    tests' real-key clients must not leak into no-key tests.)"""

    def __init__(self, key):
        self.key = key

    def __enter__(self):
        self._had = "DEEPSEEK_API_KEY" in os.environ
        self._old = os.environ.get("DEEPSEEK_API_KEY")
        self._settings = config._settings
        os.environ["DEEPSEEK_API_KEY"] = self.key
        config._settings = None
        import ai.client as _ac
        self._clients = _ac._clients
        self._model_cache = _ac._model_ids_cache
        _ac._clients = {}
        _ac._model_ids_cache = {}
        return self

    def __exit__(self, *exc):
        if self._had:
            os.environ["DEEPSEEK_API_KEY"] = self._old
        else:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        config._settings = self._settings
        import ai.client as _ac
        _ac._clients = self._clients
        _ac._model_ids_cache = self._model_cache
        return False


class _NoAutoDraft:
    """Neutralise the autonomous skill drafter for command tests:
    no file writes, no slow isolation runs."""

    def __enter__(self):
        from skills import auto_generator as _ag
        self._ag = _ag
        self._propose = _ag.propose_if_enabled
        self._handle = _ag.handle_approval_text
        _ag.propose_if_enabled = lambda *a, **k: None
        _ag.handle_approval_text = lambda *a, **k: None
        return self

    def __exit__(self, *exc):
        self._ag.propose_if_enabled = self._propose
        self._ag.handle_approval_text = self._handle
        return False


class LenientSettingsTests(unittest.TestCase):
    def test_strict_load_still_raises_on_placeholder(self):
        with _NoKeyEnv(_PLACEHOLDER):
            with self.assertRaises(ConfigError):
                Settings.load()

    def test_lenient_load_allows_placeholder(self):
        with _NoKeyEnv(_PLACEHOLDER):
            s = Settings.load(require_key=False)
            self.assertFalse(s.has_key)
            self.assertEqual(s.host, os.getenv("HOST", "127.0.0.1"))

    def test_has_key_true_for_real_key(self):
        with _NoKeyEnv("sk-live-test-value"):
            self.assertTrue(Settings.load().has_key)

    def test_try_settings_and_key_status(self):
        with _NoKeyEnv(_PLACEHOLDER):
            self.assertIsNone(config.try_settings())
            st = config.key_status()
            self.assertFalse(st["ok"])
            self.assertIn("DEEPSEEK_API_KEY", st["error"])


class NoKeyAppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls._env = _NoKeyEnv(_PLACEHOLDER)
        cls._env.__enter__()
        try:
            cls.app = create_app()
        finally:
            cls._env.__exit__(None, None, None)
        cls.app.testing = True
        cls.client = cls.app.test_client()

    def setUp(self):
        self._env = _NoKeyEnv(_PLACEHOLDER)
        self._env.__enter__()

    def tearDown(self):
        self._env.__exit__(None, None, None)
        config._settings = None

    @classmethod
    def tearDownClass(cls):
        config._settings = None

    def test_app_flags_skills_only(self):
        self.assertTrue(self.__class__.app.config["NO_KEY_MODE"])

    def test_info_reports_no_key_but_stays_200(self):
        r = self.__class__.client.get("/api/info")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertFalse(d["key"])
        self.assertTrue(d["no_key_mode"])
        self.assertTrue(len(d["skills"]) > 50)

    def test_skill_command_works_without_key(self):
        import routes.api as api
        real_speak = api.speak_async
        said = []
        api.speak_async = lambda t, **k: said.append(t)
        try:
            with _NoAutoDraft():
                r = self.__class__.client.post(
                    "/api/command", json={"text": "tell me the time"})
        finally:
            api.speak_async = real_speak
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn('"source": "skill"', body)
        self.assertIn("It is ", body)

    def test_llm_fallback_returns_setup_hint_not_500(self):
        with _NoAutoDraft():
            r = self.__class__.client.post(
                "/api/command",
                json={"text": "explain quantum entanglement simply"})
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertIn('"no_key": true', body)
        self.assertIn("Skills-only mode", body)

    def test_quiet_speak_never_raises(self):
        import routes.api as api
        real_speak = api.speak_async
        api.speak_async = lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("speaker down"))
        try:
            api._speak_quiet("hello")  # must swallow, not raise
        finally:
            api.speak_async = real_speak


if __name__ == "__main__":
    unittest.main()
