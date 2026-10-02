"""Tests for the overlay's SSE stitching (the '(no reply)' fix)."""
from __future__ import annotations
import unittest

from system.overlay import stitch_sse


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


if __name__ == "__main__":
    unittest.main()
