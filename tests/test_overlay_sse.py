"""Tests for the overlay's SSE stitching (the '(no reply)' fix)."""
from __future__ import annotations
import os
import unittest

import config
from system.overlay import _base_url, _header_text, stitch_sse


class StitchSseTests(unittest.TestCase):
    def test_skill_delta_join(self):
        lines = [
            'data: {"delta": "Hello ", "source": "skill"}',
            'data: {"delta": "world", "source": "skill"}',
            "data: [DONE]",
        ]
        self.assertEqual(stitch_sse(lines), "Hello world")

    def test_error_payload_is_surfaced(self):
        # the 1.x bug: errors were swallowed -> "(no reply)"
        lines = [
            'data: {"route": "llm"}',
            'data: {"error": "model unavailable", "detail": "x"}',
            "data: [DONE]",
        ]
        out = stitch_sse(lines)
        self.assertIn("[error] model unavailable", out)
        self.assertNotEqual(out, "(no reply)")

    def test_metadata_keys_ignored(self):
        lines = [
            'data: {"route": "tool"}',
            'data: {"reasoning": "thinking hard"}',
            'data: {"tool_call": "weather"}',
            'data: {"tool_result": "sunny"}',
            'data: {"delta": "final answer"}',
            "data: [DONE]",
            'data: {"delta": "SHOULD NOT APPEAR"}',
        ]
        self.assertEqual(stitch_sse(lines), "final answer")

    def test_plain_text_payload(self):
        lines = ["data: just plain text", "data: [DONE]"]
        self.assertEqual(stitch_sse(lines), "just plain text")

    def test_non_data_lines_ignored(self):
        lines = [": comment", "event: message", 'data: {"delta": "ok"}']
        self.assertEqual(stitch_sse(lines), "ok")

    def test_llm_stream_real_shape(self):
        lines = [
            'data: {"route": "llm"}',
            'data: {"delta": "The time "}',
            'data: {"delta": "is 18:00."}',
            "data: [DONE]",
        ]
        self.assertEqual(stitch_sse(lines), "The time is 18:00.")

    def test_empty_stream(self):
        self.assertEqual(stitch_sse(["data: [DONE]"]), "")

    def test_bytes_lines_from_urlopen(self):
        # urllib yields bytes; str(b'...') would garble the stream
        lines = [
            b'data: {"delta": "byte reply", "source": "llm"}',
            b"data: [DONE]",
        ]
        self.assertEqual(stitch_sse(lines), "byte reply")


class HeaderTextTests(unittest.TestCase):
    def test_normal_header(self):
        self.assertEqual(
            _header_text({"mood": "fast", "model": "Auto"}),
            "fast · Auto")

    def test_no_key_suffix(self):
        out = _header_text({"mood": "fast", "model": "Auto",
                            "no_key": True})
        self.assertIn("NO KEY", out)
        self.assertIn("fast", out)

    def test_missing_keys_default(self):
        self.assertEqual(_header_text({}), "? · ?")


class BaseUrlTests(unittest.TestCase):
    def test_matches_settings_with_key(self):
        s = config.Settings.load()
        self.assertEqual(_base_url(), f"http://{s.host}:{s.port}")

    def test_no_key_still_resolves(self):
        had = "DEEPSEEK_API_KEY" in os.environ
        old = os.environ.get("DEEPSEEK_API_KEY")
        saved = config._settings
        os.environ["DEEPSEEK_API_KEY"] = "sk-paste-test"
        config._settings = None
        try:
            url = _base_url()  # must not raise: HUD works skills-only
        finally:
            if had:
                os.environ["DEEPSEEK_API_KEY"] = old
            else:
                os.environ.pop("DEEPSEEK_API_KEY", None)
            config._settings = saved
        self.assertTrue(url.startswith("http://127.0.0.1:"))


if __name__ == "__main__":
    unittest.main()
