"""In-app API key setup: format validation, masked display, .env
persistence (with backup), live verification, and cache refresh —
without ever leaking the secret or touching the real .env.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import config
from config import Settings
from errors import ValidationError

_TMP_KEY = "sk-test-verify-abc123"


class _EnvGuard:
    """Snapshot os.environ key + settings/client caches, restore after."""

    def __enter__(self):
        self._had = "DEEPSEEK_API_KEY" in os.environ
        self._old = os.environ.get("DEEPSEEK_API_KEY")
        self._settings = config._settings
        import ai.client as _ac
        self._ac = _ac
        self._clients = dict(_ac._clients)
        self._mc = dict(_ac._model_ids_cache)
        self._env_path = config.ENV_PATH
        return self

    def __exit__(self, *exc):
        if self._had:
            os.environ["DEEPSEEK_API_KEY"] = self._old
        else:
            os.environ.pop("DEEPSEEK_API_KEY", None)
        config._settings = self._settings
        self._ac._clients = self._clients
        self._ac._model_ids_cache = self._mc
        config.ENV_PATH = self._env_path
        return False


class KeyFormatTests(unittest.TestCase):
    def test_validate_ok(self):
        self.assertEqual(config.validate_key_format("  sk-abc12345  "),
                         "sk-abc12345")

    def test_validate_rejects(self):
        for bad in ["", "short", "has space key 123", "sk-paste-me"]:
            with self.assertRaises(ValidationError, msg=bad):
                config.validate_key_format(bad)

    def test_masked_never_leaks(self):
        real = "sk-live-0123456789abcdef"
        with _EnvGuard():
            os.environ["DEEPSEEK_API_KEY"] = real
            config._settings = None
            masked = config.masked_key()
            self.assertNotIn(real, masked)
            self.assertTrue(masked.startswith("sk-"))
            self.assertTrue(masked.endswith(real[-4:]))
            os.environ["DEEPSEEK_API_KEY"] = "sk-paste-x"
            self.assertEqual(config.masked_key(), "")

    def test_write_env_key_replace_and_append(self):
        tmp = Path(tempfile.mkdtemp()) / ".env"
        tmp.write_text("# comment\nHOST=127.0.0.1\n"
                       "DEEPSEEK_API_KEY=sk-old\nFOO=bar\n",
                       encoding="utf-8")
        out = config.write_env_key(_TMP_KEY, tmp)
        self.assertEqual(out, tmp)
        text = tmp.read_text(encoding="utf-8")
        self.assertIn(f"DEEPSEEK_API_KEY={_TMP_KEY}", text)
        self.assertNotIn("sk-old", text)
        self.assertIn("# comment", text)
        self.assertIn("FOO=bar", text)
        bak = tmp.with_suffix(".bak")
        self.assertTrue(bak.exists())
        self.assertIn("sk-old", bak.read_text(encoding="utf-8"))

        tmp2 = Path(tempfile.mkdtemp()) / ".env"
        tmp2.write_text("HOST=x\n", encoding="utf-8")
        config.write_env_key(_TMP_KEY, tmp2)
        self.assertIn(f"DEEPSEEK_API_KEY={_TMP_KEY}",
                      tmp2.read_text(encoding="utf-8"))


class KeyEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.app = create_app()
        cls.app.testing = True
        cls.client = cls.app.test_client()

    def test_get_never_leaks_secret(self):
        with _EnvGuard():
            os.environ["DEEPSEEK_API_KEY"] = "sk-ci-test-key-123"
            config._settings = None
            r = self.__class__.client.get("/api/settings/key")
        self.assertEqual(r.status_code, 200)
        body = r.get_data(as_text=True)
        self.assertNotIn("sk-ci-test-key-123", body)
        d = json.loads(body)
        self.assertTrue(d["configured"])
        self.assertTrue(d["masked"])
        self.assertTrue(d["masked"].endswith("-123"))

    def test_post_rejects_bad_format(self):
        r = self.__class__.client.post("/api/settings/key",
                                       json={"key": "short"})
        self.assertEqual(r.status_code, 400)

    def test_post_saves_verified_key(self):
        tmp = Path(tempfile.mkdtemp()) / ".env"
        tmp.write_text("HOST=127.0.0.1\n", encoding="utf-8")
        probe = mock.MagicMock()
        probe.models.list.return_value = mock.MagicMock(data=[1, 2, 3])
        with _EnvGuard():
            config.ENV_PATH = tmp
            with mock.patch("openai.OpenAI", return_value=probe):
                r = self.__class__.client.post(
                    "/api/settings/key", json={"key": _TMP_KEY})
            live_env = os.getenv("DEEPSEEK_API_KEY")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        d = r.get_json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["verified_models"], 3)
        self.assertTrue(d["restart_recommended"])
        text = tmp.read_text(encoding="utf-8")
        self.assertIn(f"DEEPSEEK_API_KEY={_TMP_KEY}", text)
        self.assertEqual(live_env, _TMP_KEY)
        self.assertNotIn(_TMP_KEY, r.get_data(as_text=True))

    def test_post_failed_verify_saves_nothing(self):
        tmp = Path(tempfile.mkdtemp()) / ".env"
        with _EnvGuard():
            config.ENV_PATH = tmp
            with mock.patch("openai.OpenAI",
                            side_effect=RuntimeError("401 bad key")):
                r = self.__class__.client.post(
                    "/api/settings/key", json={"key": _TMP_KEY})
        self.assertEqual(r.status_code, 502)
        self.assertFalse(tmp.exists())


if __name__ == "__main__":
    unittest.main()
