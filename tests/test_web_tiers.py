"""Web tiers: Tavily keyed tier skips cleanly when keyless, Jina
reader fallback rescues pages raw HTML can't see. Tavily shapes
verified against docs.tavily.com (Bearer auth, fast depth)."""
from __future__ import annotations

import io
import json
import os
import unittest
from unittest import mock

from skills import web_search as ws


class FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._payload


def _tavily_body(items):
    return json.dumps({"results": items}).encode()


class TavilyTests(unittest.TestCase):
    def setUp(self):
        self._had = "TAVILY_API_KEY" in os.environ
        self._old = os.environ.get("TAVILY_API_KEY")
        os.environ.pop("TAVILY_API_KEY", None)

    def tearDown(self):
        if self._had:
            os.environ["TAVILY_API_KEY"] = self._old
        else:
            os.environ.pop("TAVILY_API_KEY", None)

    def test_skipped_when_keyless(self):
        self.assertEqual(ws._search_tavily("anything"), [])

    def test_rejects_placeholders(self):
        for bad in ["tvly-paste-me", "short", "   "]:
            os.environ["TAVILY_API_KEY"] = bad
            self.assertEqual(ws._search_tavily("anything"), [], bad)

    def test_success_parses_results(self):
        os.environ["TAVILY_API_KEY"] = "tvly-test-key-12345"
        body = _tavily_body([
            {"title": "T1", "url": "https://a.example",
             "content": "snippet one"},
            {"title": "T2", "url": "https://b.example", "content": "x"},
            {"title": "T3", "url": "", "content": "y"},
        ])
        seen = {}

        def fake_urlopen(req, timeout=None):
            seen["url"] = req.full_url
            seen["auth"] = req.get_header("Authorization")
            seen["body"] = json.loads(req.data.decode())
            return FakeResp(body)

        with mock.patch.object(ws.urllib.request, "urlopen",
                               side_effect=fake_urlopen):
            out = ws._search_tavily("test query", count=5)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["title"], "T1")
        self.assertTrue(out[0]["snippet"].startswith("snippet"))
        self.assertEqual(seen["url"], "https://api.tavily.com/search")
        self.assertTrue(seen["auth"].startswith("Bearer "))
        self.assertEqual(seen["body"]["search_depth"], "fast")
        self.assertEqual(seen["body"]["query"], "test query")

    def test_http_error_returns_empty(self):
        import urllib.error
        os.environ["TAVILY_API_KEY"] = "tvly-test-key-12345"

        def boom(req, timeout=None):
            raise urllib.error.HTTPError(
                req.full_url, 401, "unauthorized", {}, io.BytesIO(b"{}"))

        with mock.patch.object(ws.urllib.request, "urlopen", side_effect=boom):
            self.assertEqual(ws._search_tavily("x"), [])


class JinaFallbackTests(unittest.TestCase):
    def test_direct_hit_never_calls_jina(self):
        html = ("<html><body><p>" + "readable text. " * 30
                + "</p></body></html>")
        with mock.patch.object(ws, "_http_get",
                               return_value=html) as getter:
            out = ws.fetch_page("https://example.com")
        self.assertIn("readable text", out)
        self.assertEqual(getter.call_count, 1)

    def test_empty_direct_falls_back_to_jina(self):
        md = "# Title\n\n" + "markdown content here. " * 30
        with mock.patch.object(ws, "_http_get",
                               side_effect=["", md]) as getter:
            out = ws.fetch_page("https://example.com/js-app")
        self.assertIn("markdown content", out)
        self.assertEqual(getter.call_count, 2)
        self.assertTrue(getter.call_args[0][0].startswith(
            "https://r.jina.ai/"))

    def test_both_empty_returns_empty(self):
        with mock.patch.object(ws, "_http_get", return_value=""):
            self.assertEqual(ws.fetch_page("https://example.com/x"), "")


if __name__ == "__main__":
    unittest.main()
