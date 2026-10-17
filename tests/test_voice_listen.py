"""The /api/listen empty-result hint must name the real cause.

Speech-to-text moved to Groq, so the old "pip install faster-whisper"
hint was misleading: a missing key and a silent mic both come back as
an empty transcript.
"""
from __future__ import annotations

import unittest
from unittest import mock


class ListenHintTests(unittest.TestCase):
    def test_missing_groq_key_points_at_the_key(self):
        from routes import api_voice
        with mock.patch("config.get_settings",
                        return_value=mock.Mock(groq_api_key="")):
            hint = api_voice._listen_hint()
        self.assertIn("GROQ_API_KEY", hint)

    def test_configured_key_points_at_the_mic(self):
        from routes import api_voice
        with mock.patch("config.get_settings",
                        return_value=mock.Mock(groq_api_key="gsk_real")):
            hint = api_voice._listen_hint()
        self.assertNotIn("GROQ_API_KEY", hint)
        self.assertIn("mic", hint.lower())

    def test_never_suggests_installing_whisper(self):
        from routes import api_voice
        for key in ("", "gsk_real"):
            with mock.patch("config.get_settings",
                            return_value=mock.Mock(groq_api_key=key)):
                self.assertNotIn("faster-whisper",
                                 api_voice._listen_hint())

    def test_key_probe_failure_still_returns_a_hint(self):
        from routes import api_voice
        with mock.patch("config.get_settings",
                        side_effect=RuntimeError("no settings")):
            hint = api_voice._listen_hint()
        self.assertTrue(hint)


class ListenRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_empty_listen_carries_the_hint(self):
        from routes import api_voice
        with mock.patch.object(api_voice, "listen_until_silence",
                               return_value=None), \
                mock.patch("config.get_settings",
                           return_value=mock.Mock(groq_api_key="")):
            r = self.client.post("/api/listen")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertTrue(body.get("empty"))
        self.assertIn("GROQ_API_KEY", body.get("hint", ""))


if __name__ == "__main__":
    unittest.main()
