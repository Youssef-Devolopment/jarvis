"""system.health — /api/health snapshot, probes, and boot service marks."""
from __future__ import annotations

import unittest
from unittest import mock

from system import health


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        health.reset()

    def tearDown(self):
        health.reset()

    def test_snapshot_shape(self):
        snap = health.snapshot()
        self.assertIn("overall", snap)
        self.assertIn("checks", snap)
        self.assertIn("version", snap)
        self.assertIn("uptime_s", snap)
        self.assertIn(snap["overall"], ("ok", "warn", "degraded"))
        for key in ("config", "model", "api_key", "deps", "memory",
                    "voice", "guard", "updater", "mcp", "pending_skills",
                    "services"):
            self.assertIn(key, snap["checks"])
            self.assertIn("status", snap["checks"][key])

    def test_probe_failure_becomes_unknown_not_an_error(self):
        def _boom():
            raise RuntimeError("kaput")
        with mock.patch.dict(health._PROBES, {"boom": _boom}):
            snap = health.snapshot()
        self.assertEqual(snap["checks"]["boom"]["status"], "unknown")
        self.assertIn("kaput", snap["checks"]["boom"]["detail"])

    def test_marks_roll_up_to_services(self):
        health.mark("scheduler", True, "started")
        health.mark("tray", True)
        svc = health.snapshot()["checks"]["services"]
        self.assertEqual(svc["status"], "ok")
        self.assertEqual(len(svc["items"]), 2)
        self.assertEqual(svc["items"]["scheduler"]["detail"], "started")

    def test_failed_mark_degrades_services_and_overall(self):
        health.mark("mcp", False, "boom")
        snap = health.snapshot()
        svc = snap["checks"]["services"]
        self.assertEqual(svc["status"], "degraded")
        self.assertIn("mcp", svc["detail"])
        self.assertEqual(snap["overall"], "degraded")
        self.assertFalse(snap["ok"])

    def test_no_marks_does_not_degrade_overall(self):
        snap = health.snapshot()
        self.assertEqual(snap["checks"]["services"]["status"], "unknown")
        self.assertNotEqual(snap["overall"], "degraded")

    def test_mark_truncates_long_detail(self):
        health.mark("x", True, "y" * 500)
        item = health.snapshot()["checks"]["services"]["items"]["x"]
        self.assertLessEqual(len(item["detail"]), 200)

    def test_uptime_moves_forward(self):
        first = health.snapshot()["uptime_s"]
        self.assertGreaterEqual(first, 0)


class ProbeTests(unittest.TestCase):
    def test_updater_probe_unknown_before_first_check(self):
        from system import updater
        with mock.patch.object(updater, "last_check", return_value={}):
            res = health._probe_updater()
        self.assertEqual(res["status"], "unknown")

    def test_updater_probe_reports_available_version(self):
        from system import updater
        with mock.patch.object(updater, "last_check", return_value={
                "ok": True, "available": True, "latest": "9.9.9"}):
            res = health._probe_updater()
        self.assertEqual(res["status"], "info")
        self.assertIn("9.9.9", res["detail"])

    def test_updater_probe_warns_on_failed_check(self):
        from system import updater
        with mock.patch.object(updater, "last_check", return_value={
                "ok": False, "reason": "fetch failed"}):
            res = health._probe_updater()
        self.assertEqual(res["status"], "warn")
        self.assertIn("fetch failed", res["detail"])

    def test_config_probe_surfaces_audit_warnings(self):
        # Stub settings too: without a local .env try_settings() returns
        # None and the probe returns before the audit is consulted.
        with mock.patch("config.try_settings", return_value=object()), \
             mock.patch("config.audit_settings",
                        return_value=["PORT 70000 is outside 1-65535."]):
            res = health._probe_config()
        self.assertEqual(res["status"], "warn")
        self.assertIn("PORT 70000", res["warnings"][0])

    def test_boot_audit_prints_warning_count_line(self):
        # create_app logs each warning; a one-line COUNT follows so the
        # boot log states how bad the drift is at a glance.
        from server import create_app
        with mock.patch("config.audit_settings",
                        return_value=["PORT is weird"]), \
             self.assertLogs("server", level="WARNING") as cm:
            create_app()
        self.assertTrue(any("Config audit: 1 warning(s)" in m
                            for m in cm.output), cm.output)

    def test_memory_probe_reports_facts_and_schema(self):
        res = health._probe_memory()
        self.assertIn(res["status"], ("ok", "warn"))
        self.assertIn("facts", res)
        self.assertIn("schema", res)
        self.assertEqual(res["integrity"], "ok")

    def test_integrity_failure_degrades_memory_row(self):
        import memory
        with mock.patch.object(memory, "integrity",
                               return_value="database disk image is "
                                            "malformed"):
            res = health._probe_memory()
        self.assertEqual(res["status"], "degraded")
        self.assertIn("integrity: database", res["detail"])


class EndpointTests(unittest.TestCase):
    def test_health_route(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover - env without deps
            self.skipTest(f"app import failed: {exc}")
        health.reset()
        health.mark("scheduler", True, "started")
        client = app.test_client()
        r = client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("overall", data)
        self.assertIn("version", data)
        self.assertIn("services", data["checks"])
        self.assertIn("scheduler",
                      data["checks"]["services"]["items"])


if __name__ == "__main__":
    unittest.main()
