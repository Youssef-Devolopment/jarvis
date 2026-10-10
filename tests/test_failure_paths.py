"""Failure paths — how JARVIS degrades when a subsystem breaks.

Happy-path tests prove features work; these prove the system survives
its parts breaking: provider down, browser engine missing, voice
unavailable, memory corrupt, scheduler failing, MCP partially up,
and requests that take too long.
"""
from __future__ import annotations

import sqlite3
import unittest
from unittest import mock

from system import health, services


def _settle(name, predicate, timeout=2.0):
    """Threaded specs record their final result asynchronously — wait
    for the record to satisfy the predicate, then return it."""
    import time
    deadline = time.time() + timeout
    item = services.results().get(name, {})
    while time.time() < deadline and not predicate(item):
        time.sleep(0.02)
        item = services.results().get(name, {})
    return item


class ProviderFailureTests(unittest.TestCase):
    def setUp(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover - env without deps
            self.skipTest(f"app import failed: {exc}")
        self.client = app.test_client()

    def test_provider_down_is_structured_502_not_html(self):
        from errors import AIError
        with mock.patch("routes.api.get_client",
                        side_effect=AIError("provider down")):
            r = self.client.post("/api/command",
                                 json={"text": "hello there"})
        self.assertEqual(r.status_code, 502)
        self.assertIn("json", r.content_type or "")
        data = r.get_json()
        self.assertEqual(data["type"], "AIError")
        self.assertEqual(data["error"], "AI backend is unreachable.")

    def test_missing_key_degrades_to_hint_not_500(self):
        from errors import ConfigError
        with mock.patch("routes.api.get_client",
                        side_effect=ConfigError("no key")):
            r = self.client.post("/api/command",
                                 json={"text": "hello there"})
        body = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn("no_key", body)


class MemoryFailureTests(unittest.TestCase):
    def setUp(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover - env without deps
            self.skipTest(f"app import failed: {exc}")
        self.client = app.test_client()

    def test_corrupt_db_degrades_to_actionable_503(self):
        import memory
        with mock.patch.object(memory, "all_facts", side_effect=sqlite3.
                               DatabaseError("database disk image is "
                                             "malformed")):
            r = self.client.get("/api/memory")
        # 503 (service down, not "our bug") + instructions, never HTML.
        self.assertEqual(r.status_code, 503)
        self.assertIn("json", r.content_type or "")
        data = r.get_json()
        self.assertIn("Memory store is unavailable", data["error"])
        self.assertIn("malformed", data["detail"])
        self.assertIn("memory/backups", data["detail"])   # how to recover
        self.assertFalse((r.get_data(as_text=True) or "").lstrip()
                         .startswith("<"))   # never an HTML error page

    def test_probe_reports_memory_degradation(self):
        import memory
        with mock.patch.object(memory, "all_facts", side_effect=sqlite3.
                               DatabaseError("file is not a database")):
            res = health._probe_memory()
        self.assertEqual(res["status"], "degraded")
        self.assertIn("memory unavailable", res["detail"])


class ServiceFailureTests(unittest.TestCase):
    def setUp(self):
        health.reset()

    def tearDown(self):
        health.reset()

    def _spec(self, name, group="background", start=None, **kw):
        return services.ServiceSpec(name=name, group=group,
                                    start=start or (lambda: "ok"), **kw)

    def test_scheduler_failure_degrades_that_row_only(self):
        def boom():
            raise RuntimeError("APScheduler missing")
        specs = [self._spec("scheduler", start=boom),
                 self._spec("reminders")]
        with mock.patch.object(services, "_specs", return_value=specs):
            summary = services.boot(mode="console")
        self.assertEqual(summary["failed"], ["scheduler"])
        self.assertTrue(services.results()["reminders"]["ok"])
        snap = health.snapshot()["checks"]["services"]
        self.assertEqual(snap["status"], "degraded")
        self.assertIn("scheduler", snap["detail"])

    def test_browser_engine_missing_marks_browser_degraded(self):
        spec = next(s for s in services._specs("console")
                    if s.name == "browser")
        with mock.patch("skills.browser_agent.get_agent",
                        side_effect=ImportError("playwright missing")):
            services._run(spec)
        item = _settle("browser", lambda it: "playwright" in
                       (it.get("detail") or ""))
        self.assertFalse(item["ok"])
        self.assertIn("playwright", item["detail"])

    def test_voice_unavailable_marks_voice_degraded(self):
        spec = next(s for s in services._specs("console")
                    if s.name == "voice")
        patched = False
        try:
            ctx = mock.patch(
                "voice.warmup",
                side_effect=RuntimeError("No module named pygame"))
            ctx.start()
            self.addCleanup(ctx.stop)
            patched = True
        except Exception:
            # voice package can't even load here (missing pygame, or no
            # DEEPSEEK_API_KEY → config raises at import) — the lazy
            # starter surfaces that as the same degraded row. If the
            # starter somehow still succeeds, the settle below times out
            # on the initial record and this test fails loudly.
            pass
        services._run(spec)
        item = _settle("voice", lambda it: (it.get("detail") or "")
                       not in ("", "TTS warmed"))
        self.assertFalse(item["ok"])
        self.assertTrue(item["detail"])
        if patched:
            self.assertIn("pygame", item["detail"])

    def test_mcp_partial_failure_is_degraded(self):
        spec = next(s for s in services._specs("console")
                    if s.name == "mcp")
        with mock.patch("mcp.runtime.start_all",
                        return_value={"started": ["a"], "failed": ["b"]}):
            services._run(spec)
        item = _settle("mcp", lambda it: (it.get("detail") or "")
                       != "starting")
        self.assertFalse(item["ok"])
        self.assertIn("b", item["detail"])

    def test_mcp_all_ok_reports_count(self):
        spec = next(s for s in services._specs("console")
                    if s.name == "mcp")
        with mock.patch("mcp.runtime.start_all",
                        return_value={"started": ["a", "b"],
                                      "failed": []}):
            services._run(spec)
        item = _settle("mcp", lambda it: (it.get("detail") or "")
                       != "starting")
        self.assertTrue(item["ok"])
        self.assertIn("2 server(s)", item["detail"])


class DependencyProbeTests(unittest.TestCase):
    def test_missing_dep_warns_with_name(self):
        def fake(mod):
            return False if mod == "playwright" else True
        with mock.patch.object(health, "_has_module", side_effect=fake):
            res = health._probe_deps()
        self.assertEqual(res["status"], "warn")
        self.assertIn("playwright", res["missing"])
        self.assertIn("missing", res["detail"])

    def test_all_present_is_ok(self):
        with mock.patch.object(health, "_has_module", return_value=True):
            res = health._probe_deps()
        self.assertEqual(res["status"], "ok")

    def test_indeterminate_check_is_unknown(self):
        with mock.patch.object(health, "_has_module", return_value=None):
            res = health._probe_deps()
        self.assertEqual(res["status"], "unknown")


class ModelProbeTests(unittest.TestCase):
    def test_model_row_reports_model_and_host(self):
        s = mock.Mock(model="deepseek-chat",
                      base_url="https://tokenharbor.example/v1",
                      temperature=0.2, providers=())
        with mock.patch("config.try_settings", return_value=s):
            res = health._probe_model()
        self.assertEqual(res["status"], "ok")
        self.assertIn("deepseek-chat", res["detail"])
        self.assertIn("tokenharbor.example", res["detail"])
        self.assertEqual(res["base_host"], "tokenharbor.example")

    def test_settings_unreadable_is_unknown(self):
        with mock.patch("config.try_settings", return_value=None):
            res = health._probe_model()
        self.assertEqual(res["status"], "unknown")


class SlowRequestTests(unittest.TestCase):
    def test_slow_request_is_logged(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover - env without deps
            self.skipTest(f"app import failed: {exc}")
        client = app.test_client()
        with mock.patch("server.SLOW_REQUEST_S", 0):
            with self.assertLogs("server", level="WARNING") as cm:
                client.get("/api/info")
        self.assertTrue(any("Slow request" in line
                            for line in cm.output), cm.output)


if __name__ == "__main__":
    unittest.main()
