"""Service lifecycle control — stop/restart one boot service safely.

Registry units (describe/stop_service/restart) plus the
POST /api/services/<name> endpoint the SYSTEM tab buttons call.
Route tests never cycle a real service: the catalog is patched or a
no-handler/boot-only refusal path (which raises before any handler
runs) is exercised directly.
"""
from __future__ import annotations

import time
import unittest
from unittest import mock

from system import health, services


def _spec(name="cyc", group="background", start=None, **kw):
    return services.ServiceSpec(name=name, group=group,
                                start=start or (lambda: "up"), **kw)


def _settle(name, predicate, timeout=2.0):
    deadline = time.time() + timeout
    item = services.results().get(name, {})
    while time.time() < deadline and not predicate(item):
        time.sleep(0.02)
        item = services.results().get(name, {})
    return item


class DescribeTests(unittest.TestCase):
    def setUp(self):
        health.reset()

    def tearDown(self):
        health.reset()

    def test_unknown_service_is_none(self):
        self.assertIsNone(services.describe("ghost"))

    def test_describe_exposes_flags_and_current_state(self):
        stopper = mock.Mock()
        spec = _spec(stop=stopper)
        with mock.patch.object(services, "_specs", return_value=[spec]):
            services._run(spec)
            info = services.describe("cyc")
        self.assertTrue(info["stoppable"])
        self.assertTrue(info["restartable"])
        self.assertEqual(info["group"], "background")
        self.assertTrue(info["ok"])

    def test_warmup_one_shot_is_restartable_but_not_stoppable(self):
        with mock.patch.object(services, "_specs",
                               return_value=[_spec(name="warm")]):
            info = services.describe("warm")
        self.assertFalse(info["stoppable"])
        self.assertTrue(info["restartable"])

    def test_boot_only_listener_refuses_restart(self):
        spec = _spec(name="listen", group="desktop", restartable=False)
        with mock.patch.object(services, "_specs", return_value=[spec]):
            info = services.describe("listen")
        self.assertFalse(info["restartable"])

    def test_control_flags_reach_health_services_items(self):
        spec = _spec(name="flagged", stop=mock.Mock())
        with mock.patch.object(services, "_specs", return_value=[spec]):
            services._run(spec)
            item = health.snapshot()["checks"]["services"]["items"]["flagged"]
        self.assertTrue(item["stoppable"])
        self.assertTrue(item["restartable"])


class StopRestartTests(unittest.TestCase):
    def setUp(self):
        health.reset()

    def tearDown(self):
        health.reset()

    def test_stop_calls_handler_and_records_stopped(self):
        stopper = mock.Mock(return_value=None)
        with mock.patch.object(services, "_specs",
                               return_value=[_spec(stop=stopper)]):
            rec = services.stop_service("cyc")
        stopper.assert_called_once()
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["detail"], "stopped")

    def test_stop_uses_handler_return_value_as_detail(self):
        stopper = mock.Mock(return_value="stopped 3 server(s)")
        with mock.patch.object(services, "_specs",
                               return_value=[_spec(stop=stopper)]):
            rec = services.stop_service("cyc")
        self.assertEqual(rec["detail"], "stopped 3 server(s)")

    def test_stop_unknown_service_raises(self):
        with mock.patch.object(services, "_specs", return_value=[]):
            with self.assertRaises(ValueError):
                services.stop_service("ghost")

    def test_stop_without_handler_raises(self):
        with mock.patch.object(services, "_specs",
                               return_value=[_spec(name="warm")]):
            with self.assertRaises(ValueError) as ctx:
                services.stop_service("warm")
        self.assertIn("no stop handler", str(ctx.exception))

    def test_failed_stop_records_degraded_row(self):
        stopper = mock.Mock(side_effect=RuntimeError("cannot stop"))
        with mock.patch.object(services, "_specs",
                               return_value=[_spec(stop=stopper)]):
            rec = services.stop_service("cyc")
        self.assertFalse(rec["ok"])
        self.assertIn("stop failed", rec["detail"])
        self.assertIn("cannot stop", rec["detail"])

    def test_restart_stops_then_starts_in_order(self):
        order = []
        spec = _spec(start=lambda: order.append("start"),
                     stop=lambda: order.append("stop"))
        with mock.patch.object(services, "_specs", return_value=[spec]):
            services._run(spec)
            order.clear()
            rec = services.restart("cyc")
        self.assertEqual(order, ["stop", "start"])
        self.assertTrue(rec["ok"])

    def test_restart_without_stop_handler_starts_only(self):
        order = []
        with mock.patch.object(services, "_specs",
                               return_value=[_spec(
                                   start=lambda: order.append("start"))]):
            rec = services.restart("cyc")
        self.assertEqual(order, ["start"])
        self.assertTrue(rec["ok"])

    def test_failed_stop_does_not_abort_the_start(self):
        spec = _spec(start=lambda: "running",
                     stop=mock.Mock(side_effect=RuntimeError("stuck")))
        with mock.patch.object(services, "_specs", return_value=[spec]):
            rec = services.restart("cyc")
        self.assertTrue(rec["ok"])
        self.assertEqual(rec["detail"], "running")

    def test_failed_start_is_recorded_not_raised(self):
        def boom():
            raise RuntimeError("wont start")
        spec = _spec(start=boom, stop=mock.Mock())
        with mock.patch.object(services, "_specs", return_value=[spec]):
            rec = services.restart("cyc")
        self.assertFalse(rec["ok"])
        self.assertIn("wont start", rec["detail"])

    def test_restart_boot_only_service_refused(self):
        with mock.patch.object(services, "_specs",
                               return_value=[_spec(name="listen",
                                                   restartable=False)]):
            with self.assertRaises(ValueError) as ctx:
                services.restart("listen")
        self.assertIn("boot-only", str(ctx.exception))

    def test_restart_threaded_lands_asynchronously(self):
        spec = _spec(threaded=True, start=lambda: "reborn")
        with mock.patch.object(services, "_specs", return_value=[spec]):
            rec = services.restart("cyc")
            self.assertTrue(rec["ok"])          # transient "starting" record
            item = _settle("cyc",
                           lambda i: i.get("detail") == "reborn")
        self.assertEqual(item["detail"], "reborn")
        self.assertTrue(item["ok"])


class ServiceControlRouteTests(unittest.TestCase):
    def setUp(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover - env without deps
            self.skipTest(f"app import failed: {exc}")
        self.client = app.test_client()
        health.reset()

    def tearDown(self):
        health.reset()

    def test_unknown_service_is_400(self):
        r = self.client.post("/api/services/ghost", json={"action": "stop"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("json", r.content_type or "")
        self.assertIn("Unknown service", r.get_json()["detail"])

    def test_missing_action_is_400(self):
        r = self.client.post("/api/services/clipboard", json={})
        self.assertEqual(r.status_code, 400)
        self.assertIn("action", r.get_json()["detail"])

    def test_unknown_action_is_400(self):
        r = self.client.post("/api/services/clipboard",
                             json={"action": "explode"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("stop", r.get_json()["detail"])

    def test_stop_without_handler_is_400(self):
        # voice is a warmup one-shot — describe finds the real spec and
        # stop_service refuses BEFORE touching any handler.
        r = self.client.post("/api/services/voice", json={"action": "stop"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("no stop handler", r.get_json()["detail"])

    def test_restart_boot_only_service_is_400(self):
        r = self.client.post("/api/services/hotkeys",
                             json={"action": "restart"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("boot-only", r.get_json()["detail"])

    def test_successful_stop_returns_200_with_service_record(self):
        with mock.patch("system.services.stop_service",
                        return_value={"ok": True, "detail": "stopped",
                                      "group": "background", "ms": 1}):
            r = self.client.post("/api/services/clipboard",
                                 json={"action": "stop"})
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["name"], "clipboard")
        self.assertEqual(data["action"], "stop")
        self.assertTrue(data["service"]["ok"])

    def test_successful_restart_returns_200(self):
        with mock.patch("system.services.restart",
                        return_value={"ok": True, "detail": "started",
                                      "group": "background", "ms": 4}):
            r = self.client.post("/api/services/clipboard",
                                 json={"action": "restart"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["action"], "restart")

    def test_failed_stop_handler_is_400_with_detail(self):
        with mock.patch("system.services.stop_service",
                        return_value={"ok": False,
                                      "detail": "stop failed: stuck"}):
            r = self.client.post("/api/services/clipboard",
                                 json={"action": "stop"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("stop failed: stuck", r.get_json()["detail"])


if __name__ == "__main__":
    unittest.main()
