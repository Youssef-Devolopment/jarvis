"""Web delivery contracts - what the browser actually has to fetch.

Three things measured on a live boot in 1.37.0 and worth not losing:

1. The page shipped 212,941 bytes uncompressed. gzip takes that to
   49,171 (76.9% smaller) with the bodies byte-identical.
2. Static carried ``Cache-Control: no-cache``, so the browser revalidated
   every asset on every load even though every link already carries
   ``?v=<config.VERSION>`` as its cache-buster.
3. The font stylesheet came from a CDN *and* was render-blocking, which
   means first paint waited on a third-party round trip - in an app that
   advertises itself as local-first.

Each contract is cheap to break by accident: adding ``direct_passthrough``
back, dropping the ``?v=``, or "tidying" the font link into a plain
stylesheet all look harmless in isolation.
"""
import gzip
import re
import time
import unittest
from pathlib import Path

from server import create_app

ROOT = Path(__file__).resolve().parents[1]
GZIP = {"Accept-Encoding": "gzip"}
FONT_URL = "fonts.googleapis.com"


def _html():
    return (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


class GzipTests(unittest.TestCase):
    """The page and its assets go over the wire compressed."""

    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()
        cls.js = (ROOT / "static" / "js" / "app.js").read_bytes()

    def test_the_big_assets_are_compressed(self):
        for path in ("/", "/static/js/app.js", "/static/css/style.css"):
            with self.subTest(path=path):
                r = self.client.get(path, headers=GZIP)
                self.assertEqual(r.headers.get("Content-Encoding"), "gzip",
                                 f"{path} is served uncompressed")

    def test_compressed_body_is_the_same_bytes(self):
        """Compression must not be allowed to alter what is delivered."""
        r = self.client.get("/static/js/app.js", headers=GZIP)
        self.assertEqual(gzip.decompress(r.data), self.js)

        plain = self.client.get("/")
        zipped = self.client.get("/", headers=GZIP)
        self.assertEqual(gzip.decompress(zipped.data), plain.data)

    def test_json_endpoints_are_compressed(self):
        r = self.client.get("/api/prefs", headers=GZIP)
        self.assertEqual(r.headers.get("Content-Encoding"), "gzip")
        self.assertIn("Vary", r.headers)  # caches must keep the copies apart

    def test_no_compression_unless_the_client_asks(self):
        """Sending gzip to a client that cannot read it is a hard failure."""
        for headers in (None, {"Accept-Encoding": "identity"},
                        {"Accept-Encoding": "br"}):
            with self.subTest(headers=headers):
                r = self.client.get("/static/js/app.js", headers=headers)
                self.assertIsNone(r.headers.get("Content-Encoding"))
                self.assertEqual(r.data, self.js)


class StreamSafetyTests(unittest.TestCase):
    """Compression must never buffer a stream that has to flush."""

    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.client = cls.app.test_client()

    def test_sse_replies_are_never_compressed(self):
        """The /api/command stream flushes event by event.

        Reading it whole would hold every event until the stream ended,
        which is precisely what a stream exists to avoid.
        """
        from flask import Response

        def events():
            yield b"event: delta\n"
            yield b"data: {}\n\n"

        with self.app.test_request_context("/", headers=GZIP):
            resp = Response(events(), mimetype="text/event-stream")
            from server import _gzip_response
            _gzip_response(resp)
            self.assertNotIn("Content-Encoding", resp.headers)

    def test_other_live_streams_are_left_alone(self):
        """Defence in depth: not just the one content type we know about."""
        from flask import Response

        def chunks():
            yield b"x" * 4096

        with self.app.test_request_context("/", headers=GZIP):
            resp = Response(chunks(), mimetype="application/x-ndjson")
            self.assertTrue(resp.is_streamed)
            self.assertFalse(resp.direct_passthrough)
            from server import _gzip_response
            _gzip_response(resp)
            self.assertNotIn("Content-Encoding", resp.headers)

    def test_a_gzip_failure_never_breaks_the_response(self):
        """The speedup is optional; the response is not."""
        from flask import Response

        from server import _gzip_response

        with self.app.test_request_context("/", headers=GZIP):
            resp = Response(b"ok", mimetype="text/plain")
            real_get_data = resp.get_data

            def boom(*_a, **_kw):
                raise RuntimeError("boom")

            resp.get_data = boom
            _gzip_response(resp)  # must swallow the failure, not raise
            resp.get_data = real_get_data
            self.assertEqual(resp.get_data(), b"ok")
            self.assertNotIn("Content-Encoding", resp.headers)


class CacheTests(unittest.TestCase):
    """Versioned assets may be cached hard; everything else may not."""

    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()

    def test_versioned_static_is_immutable(self):
        r = self.client.get("/static/js/app.js?v=9.9.9")
        cc = r.headers.get("Cache-Control", "")
        self.assertIn("immutable", cc)
        self.assertIn("max-age=31536000", cc)

    def test_unversioned_static_is_not_marked_immutable(self):
        """Without ?v= there is no cache-buster, so a stale copy would stick."""
        r = self.client.get("/static/js/app.js")
        self.assertNotIn("immutable", r.headers.get("Cache-Control", ""))

    def test_every_static_link_carries_the_cache_buster(self):
        """immutable is only safe because ?v= exists to invalidate it."""
        links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', _html())
        static_links = [href for href in links if "static" in href]
        self.assertTrue(static_links, "no local stylesheet link found")
        for link in static_links:
            with self.subTest(link=link):
                self.assertIn("?v=", link)

    def test_conditional_requests_still_work(self):
        """gzip runs before Werkzeug's conditional pass - it must not eat it."""
        first = self.client.get("/static/js/app.js")
        etag = first.headers.get("ETag")
        self.assertTrue(etag, "static assets should expose a validator")
        second = self.client.get("/static/js/app.js",
                                 headers={"If-None-Match": etag, **GZIP})
        self.assertEqual(second.status_code, 304)


class FontTests(unittest.TestCase):
    """The CDN font stylesheet must not gate first paint."""

    def test_font_stylesheet_is_not_render_blocking(self):
        html = _html()
        # Ignore the <noscript> fallbacks: those are already off the
        # critical path by definition (no JS = no async swap available).
        without_noscript = re.sub(r"<noscript>.*?</noscript>", "", html,
                                  flags=re.S)
        links = [m for m in re.findall(r"<link[^>]+>", without_noscript)
                 if FONT_URL in m and 'rel="stylesheet"' in m]
        self.assertTrue(links, "the font stylesheet link is gone")
        for link in links:
            with self.subTest(link=link[:80]):
                self.assertIn('media="print"', link,
                              "font stylesheet blocks rendering again")

    def test_fonts_are_preloaded_and_fall_back_locally(self):
        html = _html()
        self.assertIn('rel="preload" as="style"', html.replace("\n ", " "))
        css = (ROOT / "static" / "css" / "style.css").read_text(
            encoding="utf-8")
        for family in ("--sans", "--mono", "--display"):
            with self.subTest(var=family):
                self.assertRegex(css, rf"{family}:\s*'[^']+',\s*[\w-]+",
                                 f"{family} has no offline fallback face")


class StatsTests(unittest.TestCase):
    """/api/stats must not sleep to sample a number shown every 3s."""

    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()
        cls.src = (ROOT / "routes" / "api_core.py").read_text(
            encoding="utf-8")

    def test_cpu_is_sampled_without_blocking(self):
        """interval=0.1 slept ~109ms inside the request; None costs ~0.5ms."""
        self.assertIn("cpu_percent(interval=None)", self.src)
        self.assertNotIn("cpu_percent(interval=0.1)", self.src,
                         "/api/stats went back to sleeping in the request")

    def test_stats_returns_the_four_sidebar_numbers(self):
        r = self.client.get("/api/stats")
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        for key in ("cpu", "ram", "battery", "net"):
            self.assertIn(key, body)

    def test_the_expensive_network_query_is_cached(self):
        """net_io_counters() costs ~23ms and its value only ever grows.

        A 3s poll does not need a fresh perf-counter query every hit, so
        the second call inside the TTL must not reach psutil at all.
        """
        from routes import api_core

        calls = {"n": 0}
        import psutil
        real = psutil.net_io_counters

        def counting(*a, **kw):
            calls["n"] += 1
            return real(*a, **kw)

        saved = api_core._NET_CACHE["at"]
        api_core._NET_CACHE["at"] = time.monotonic() - 1000  # force a miss
        psutil.net_io_counters = counting
        try:
            first = api_core._net_total_mb()
            second = api_core._net_total_mb()
        finally:
            psutil.net_io_counters = real
            api_core._NET_CACHE["at"] = saved
        self.assertEqual(calls["n"], 1, "the cached call hit psutil again")
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
