"""system.services — the shared service registry both boot paths use.

This module exists to kill a real bug: run.py (console) and
system/launcher.py (desktop) each had their own copy-pasted start
blocks, so desktop never started reminders/scheduler/dream/clipboard/
time-tracker/sentinel/MCP while console did. One registry, one boot.
"""
from __future__ import annotations

import time
import unittest
from unittest import mock

from system import health, services


def _spec(name="demo", group="background", start=None, **kw):
    return services.ServiceSpec(name=name, group=group,
                                start=start or (lambda: "ok"), **kw)


class RegistryTests(unittest.TestCase):
    def setUp(self):
        health.reset()          # clears marks AND registry results

    def tearDown(self):
        health.reset()

    def test_result_shape_and_snapshot_is_a_copy(self):
        services._run(_spec(name="demo"))
        res = services.results()
        item = res["demo"]
        self.assertTrue(item["ok"])
        self.assertEqual(item["group"], "background")
        self.assertEqual(item["detail"], "ok")
        self.assertIsInstance(item["ms"], int)
        res["demo"]["ok"] = False               # mutating the snapshot
        self.assertTrue(services.results()["demo"]["ok"])  # is safe

    def test_detail_truncated_to_200_chars(self):
        services._run(_spec(name="long", start=lambda: "x" * 500))
        self.assertEqual(len(services.results()["long"]["detail"]), 200)

    def test_failed_start_recorded_with_error(self):
        def boom():
            raise RuntimeError("kaput")
        services._run(_spec(name="bad", start=boom))
        item = services.results()["bad"]
        self.assertFalse(item["ok"])
        self.assertIn("kaput", item["detail"])

    def test_false_return_counts_as_failed(self):
        # scheduler.start() returns False when APScheduler is missing —
        # "did not start" must not read as healthy.
        services._run(_spec(name="declined", start=lambda: False))
        self.assertFalse(services.results()["declined"]["ok"])

    def test_pref_disabled_service_never_starts(self):
        starter = mock.Mock()
        spec = _spec(name="gated", start=starter, pref="some_pref")
        with mock.patch("memory.get_pref", return_value=False):
            services._run(spec)
        starter.assert_not_called()
        item = services.results()["gated"]
        self.assertTrue(item["ok"])
        self.assertEqual(item["detail"], "disabled by pref")

    def test_threaded_service_records_eventually(self):
        services._run(_spec(name="asyncy", threaded=True,
                            start=lambda: "done"))
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if services.results().get("asyncy", {}).get("detail") == "done":
                break
            time.sleep(0.02)
        self.assertEqual(services.results()["asyncy"]["detail"], "done")

    def test_result_is_visible_to_health_services(self):
        services._run(_spec(name="mirror"))
        snap = health.snapshot()["checks"]["services"]
        self.assertIn("mirror", snap["items"])
        self.assertTrue(snap["items"]["mirror"]["ok"])


class BootTests(unittest.TestCase):
    def setUp(self):
        health.reset()

    def tearDown(self):
        health.reset()

    def test_boot_never_raises_even_if_every_service_fails(self):
        def boom():
            raise RuntimeError("everything broken")
        specs = [_spec(name=f"s{i}", start=boom) for i in range(3)]
        with mock.patch.object(services, "_specs", return_value=specs):
            summary = services.boot(mode="console")
        self.assertEqual(summary["launched"], 3)
        self.assertEqual(sorted(summary["failed"]), ["s0", "s1", "s2"])

    def test_one_failure_does_not_stop_the_others(self):
        def boom():
            raise RuntimeError("nope")
        specs = [_spec(name="good1"), _spec(name="bad", start=boom),
                 _spec(name="good2")]
        with mock.patch.object(services, "_specs", return_value=specs):
            summary = services.boot(mode="console")
        self.assertEqual(summary["failed"], ["bad"])
        self.assertTrue(services.results()["good1"]["ok"])
        self.assertTrue(services.results()["good2"]["ok"])

    def test_only_filter_limits_boot(self):
        specs = [_spec(name="a"), _spec(name="b")]
        with mock.patch.object(services, "_specs", return_value=specs):
            summary = services.boot(mode="console", only=["b"])
        self.assertEqual(summary["launched"], 1)
        self.assertIn("b", services.results())
        self.assertNotIn("a", services.results())

    def test_boot_summary_reports_pref_skips(self):
        spec = _spec(name="gated", pref="some_pref")
        with mock.patch.object(services, "_specs", return_value=[spec]), \
             mock.patch("memory.get_pref", return_value=False):
            summary = services.boot(mode="console")
        self.assertEqual(summary["skipped"], ["gated"])
        self.assertEqual(summary["failed"], [])

    def test_boot_records_timing(self):
        with mock.patch.object(services, "_specs",
                               return_value=[_spec(name="fast")]):
            summary = services.boot(mode="console")
        self.assertIsInstance(summary["ms"], int)
        self.assertGreaterEqual(summary["ms"], 0)


class SpecCatalogTests(unittest.TestCase):
    def test_overlay_only_boots_on_desktop(self):
        names_c = {s.name for s in services._specs("console")}
        names_d = {s.name for s in services._specs("desktop")}
        self.assertNotIn("overlay", names_c)
        self.assertIn("overlay", names_d)

    def test_every_spec_uses_a_known_group(self):
        for mode in ("console", "desktop"):
            for spec in services._specs(mode):
                self.assertIn(spec.group, services.GROUPS, spec.name)

    def test_core_services_present_in_both_modes(self):
        for mode in ("console", "desktop"):
            names = {s.name for s in services._specs(mode)}
            for core in ("updater", "guard", "scheduler", "reminders",
                         "dream", "clipboard", "time_tracker",
                         "folder_sentinel", "voice", "browser", "mcp",
                         "tray", "hotkeys"):
                self.assertIn(core, names, f"{core} missing in {mode}")

    def test_both_modes_start_the_same_service_set(self):
        """Regression guard for the split-brain this module fixes."""
        c = {s.name for s in services._specs("console")}
        d = {s.name for s in services._specs("desktop")}
        self.assertEqual(c, d - {"overlay"})


if __name__ == "__main__":
    unittest.main()
