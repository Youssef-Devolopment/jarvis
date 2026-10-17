"""v1.28.0 — one-time MCP SDK import.

The _sdk() sys.modules surgery used to run on EVERY server spawn, so
every boot opened ~11 windows where a concurrent local import died
with "cannot import name 'all_servers' from 'mcp'" (and killed the
Flask thread with it). Now the surgery runs once per process (cached)
and both entry points prewarm it single-threaded before threads
spread. Contracts: same tuple identity, failure cached too, local
package intact afterwards, prewarm never raises.
"""
import asyncio
import threading
import unittest
from unittest import mock


class SdkCacheTests(unittest.TestCase):
    def setUp(self):
        from mcp import runtime
        self.rt = runtime
        self.saved = runtime._sdk_cache
        runtime._sdk_cache = None
        self.addCleanup(setattr, runtime, "_sdk_cache", self.saved)

    def test_second_call_hits_cache_without_surgery(self):
        first = self.rt._sdk()
        with mock.patch.object(
                self.rt, "_sdk_uncached",
                side_effect=AssertionError("surgery ran twice")):
            second = self.rt._sdk()
        self.assertIs(first, second)
        self.assertIsNotNone(self.rt._sdk_cache)

    def test_concurrent_calls_share_one_surgery(self):
        seen = []
        orig = self.rt._sdk_uncached
        gate = threading.Event()

        def slow_surgery():
            gate.wait(5)
            return orig()

        with mock.patch.object(self.rt, "_sdk_uncached",
                               side_effect=lambda: slow_surgery()):
            threads = [threading.Thread(target=lambda: seen.append(
                self.rt._sdk())) for _ in range(4)]
            for t in threads:
                t.start()
            gate.set()
            for t in threads:
                t.join(timeout=30)
        self.assertEqual(len(seen), 4)
        self.assertTrue(all(s is seen[0] for s in seen))

    def test_local_package_intact_after_surgery(self):
        self.rt._sdk()
        import mcp as local
        self.assertTrue(hasattr(local, "all_servers"))
        self.assertTrue(hasattr(local, "runtime"))
        from mcp import all_servers, runtime  # noqa — the boot import
        self.assertTrue(callable(all_servers))

    def test_failure_caches_as_import_error(self):
        with mock.patch.object(
                self.rt, "_sdk_uncached",
                side_effect=[ImportError("no sdk"), AssertionError(
                    "second surgery")]) as m:
            with self.assertRaises(ImportError):
                self.rt._sdk()
            with self.assertRaises(ImportError):
                self.rt._sdk()
            self.assertEqual(m.call_count, 1)

    def test_start_server_degrades_without_sdk(self):
        async def go():
            with mock.patch.object(
                    self.rt, "_sdk",
                    side_effect=ImportError("no sdk")):
                return await self.rt._start_server({"name": "x"})
        out = asyncio.new_event_loop().run_until_complete(go())
        self.assertIsNone(out)

    def test_prewarm_true_and_never_raises(self):
        self.assertTrue(self.rt.prewarm())
        with mock.patch.object(self.rt, "_sdk",
                               side_effect=RuntimeError("boom")):
            self.assertFalse(self.rt.prewarm())


if __name__ == "__main__":
    unittest.main()
