"""First-run product surface — Phase 1 trust & usability.

Three things a first-time user meets, tested for honesty and safety:
  * system.startup  — boot status block, safe-mode verdicts, toasts,
    friendly bind errors (all derived from ONE health snapshot);
  * check.py        — capability summary, bucket classification and
    the 0/1/2 exit codes setup scripts branch on;
  * everything here must degrade to a line, never raise.
"""
from __future__ import annotations

import dataclasses
import unittest
from unittest import mock

import check
from config import Settings
from system import startup


def _settings(**over):
    """Settings with every field None, then explicit overrides."""
    vals = {f.name: None for f in dataclasses.fields(Settings)}
    vals.update(dict(model="deepseek-chat", host="127.0.0.1", port=5001,
                     voice_name="en-GB-Ryan", debug=False))
    vals.update(over)
    return Settings(**vals)


def _snap(overall, checks):
    return {"overall": overall, "checks": checks}


def _row(lines, name):
    """Value of a capability row like '    AI chat   : on'."""
    for line in lines.splitlines():
        if line.strip().startswith(name):
            return line.split(name, 1)[1].lstrip(" :")
    return None


class StatusLinesTests(unittest.TestCase):
    def test_full_mode_lists_model_and_url(self):
        text = "\n".join(startup.status_lines(_settings()))
        self.assertIn("JARVIS v", text)
        self.assertIn("http://127.0.0.1:5001", text)
        self.assertIn("deepseek-chat", text)
        self.assertNotIn("SKILLS-ONLY", text)

    def test_skills_only_says_what_works_what_doesnt_and_the_fix(self):
        text = "\n".join(
            startup.status_lines(_settings(api_key=None), skills_only=True))
        self.assertIn("SKILLS-ONLY mode", text)
        self.assertIn("Works now", text)
        self.assertIn("Not yet", text)
        self.assertIn("Settings -> GENERAL", text)   # how to fix setup
        self.assertIn("DEEPSEEK_API_KEY", text)

    def test_empty_voice_name_is_explicit_not_blank(self):
        text = "\n".join(startup.status_lines(_settings(voice_name="")))
        self.assertIn("VOICE_NAME empty", text)

    def test_broken_memory_degrades_to_line_not_crash(self):
        with mock.patch("memory.all_facts",
                        side_effect=OSError("disk error")):
            lines = startup.status_lines(_settings())
        mem = [l for l in lines if l.strip().startswith("Memory")]
        self.assertTrue(mem, lines)
        self.assertIn("UNAVAILABLE", mem[0])

    def test_broken_moods_degrades_to_line_not_crash(self):
        with mock.patch("moods.current_name",
                        side_effect=RuntimeError("boom")):
            lines = startup.status_lines(_settings())
        self.assertTrue(any(l.strip().startswith("Mood") and
                            "unavailable" in l for l in lines), lines)


class SafeModeBlockTests(unittest.TestCase):
    def test_clean_boot_prints_nothing(self):
        self.assertEqual(startup.safe_mode_block([]), [])

    def test_block_names_loss_works_and_next_step(self):
        text = "\n".join(startup.safe_mode_block(["mcp"], healthy=16))
        self.assertIn("SAFE MODE", text)
        self.assertIn("mcp", text)
        self.assertIn("external MCP tools", text)     # what's broken
        self.assertIn("16 of 17 services", text)      # what works
        self.assertIn("Settings -> SYSTEM", text)     # what to do next

    def test_unknown_service_falls_back_to_pretty_name(self):
        text = "\n".join(startup.safe_mode_block(["weird_thing"]))
        self.assertIn("weird thing", text)

    def test_skills_only_excludes_llm_chat_from_works(self):
        with_chat = "\n".join(startup.safe_mode_block(["mcp"]))
        without = "\n".join(startup.safe_mode_block(["mcp"],
                                                    skills_only=True))
        self.assertIn("LLM chat", with_chat)
        self.assertNotIn("LLM chat", without)


class HealthBlockTests(unittest.TestCase):
    """The startup verdict derives from the /api/health snapshot."""

    def test_ok_is_one_reassurance_line(self):
        lines = startup.health_block(
            _snap("ok", {"api_key": {"status": "ok"},
                         "services": {"items": {}}}))
        self.assertTrue(any("OK — all systems healthy" in l
                            for l in lines), lines)

    def test_ok_with_pending_service_says_still_starting(self):
        snap = _snap("ok", {
            "api_key": {"status": "ok"},
            "services": {"items": {"mcp": {"ok": True, "detail": "starting"}}}})
        text = "\n".join(startup.health_block(snap))
        self.assertIn("still starting: mcp", text)   # never lie early
        self.assertNotIn("all systems healthy", text)

    def test_warn_counts_config_warnings_and_points_at_details(self):
        snap = _snap("warn", {
            "api_key": {"status": "ok"},
            "config": {"status": "warn", "warnings": ["PORT is weird"]}})
        text = "\n".join(startup.health_block(snap))
        self.assertIn("WARN — 1 config warning(s)", text)
        self.assertIn("PORT is weird", text)
        self.assertIn("Settings -> SYSTEM", text)

    def test_failed_service_gets_safe_mode_block(self):
        snap = _snap("degraded", {
            "api_key": {"status": "ok"},
            "services": {"items": {"voice": {"ok": False, "detail": "boom"},
                                   "mcp": {"ok": True, "detail": "5 running"}}}})
        text = "\n".join(startup.health_block(snap))
        self.assertIn("SAFE MODE", text)
        self.assertIn("voice", text)
        self.assertIn("1 of 2 services failed", text)
        self.assertIn("speech input/output", text)

    def test_probe_level_degradation_without_service_failure(self):
        snap = _snap("degraded", {
            "api_key": {"status": "ok"},
            "memory": {"status": "degraded", "detail": "integrity: bad"},
            "services": {"items": {}}})
        text = "\n".join(startup.health_block(snap))
        self.assertIn("SAFE MODE — degraded: memory", text)
        self.assertIn("integrity: bad", text)

    def test_skills_only_is_derived_from_the_api_key_check(self):
        snap = _snap("degraded", {
            "api_key": {"status": "warn"},
            "services": {"items": {"mcp": {"ok": False}}}})
        text = "\n".join(startup.health_block(snap))
        self.assertNotIn("LLM chat", text)   # no key -> don't promise chat


class ToastTests(unittest.TestCase):
    def test_clean_boot_toast_says_how_to_open(self):
        self.assertEqual(startup.toast_status(), "Press Ctrl+Alt+J to open")

    def test_skills_only_toast_is_honest(self):
        self.assertIn("Skills-only",
                      startup.toast_status([], has_key=False))

    def test_failed_boot_toast_names_services_and_next_step(self):
        msg = startup.toast_status(["mcp", "voice"])
        self.assertIn("Safe mode", msg)
        self.assertIn("mcp", msg)
        self.assertIn("SYSTEM", msg)

    def test_degraded_toast_none_when_healthy(self):
        snap = _snap("ok", {"services": {"items": {"mcp": {"ok": True}}}})
        self.assertIsNone(startup.degraded_toast(snap))

    def test_degraded_toast_names_failed_service(self):
        snap = _snap("degraded",
                     {"services": {"items": {"mcp": {"ok": False}}}})
        msg = startup.degraded_toast(snap)
        self.assertIn("mcp", msg)
        self.assertIn("SYSTEM", msg)

    def test_toast_if_degraded_only_toasts_when_degraded(self):
        healthy = _snap("ok", {"services": {"items": {"mcp": {"ok": True}}}})
        broken = _snap("degraded",
                       {"services": {"items": {"mcp": {"ok": False}}}})
        with mock.patch("system.notify.toast") as t:
            startup.toast_if_degraded(healthy)
            t.assert_not_called()
            startup.toast_if_degraded(broken)
            t.assert_called_once()


class BindErrorTests(unittest.TestCase):
    def test_bind_error_is_friendly_actionable_no_traceback(self):
        msg = startup.bind_error(OSError(10048, "in use"),
                                 "127.0.0.1", 5001)
        self.assertIn("127.0.0.1:5001", msg)
        self.assertIn("PORT in .env", msg)
        self.assertIn("jarvis.lock", msg)
        self.assertNotIn("Traceback", msg)


class EnsurePortTests(unittest.TestCase):
    def test_free_port_probes_clean(self):
        import socket
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        self.assertIsNone(startup.ensure_port("127.0.0.1", port))

    def test_held_port_returns_error_text(self):
        import socket
        s = socket.socket()
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.listen(1)
        try:
            err = startup.ensure_port("127.0.0.1", port)
            self.assertTrue(err, "held port must produce an error")
        finally:
            s.close()

    def test_garbage_port_never_blocks_boot(self):
        self.assertIsNone(startup.ensure_port("127.0.0.1", "not-a-port"))


class PreflightTests(unittest.TestCase):
    """check.py — buckets, exit codes, capability summary, hints."""

    @staticmethod
    def _res(*items):
        return [(ok, lbl, detail, check.bucket(lbl))
                for ok, lbl, detail in items]

    def test_every_check_has_an_actionable_hint(self):
        for label, _fn in check.CHECKS:
            self.assertIn(label, check.HINTS, label)

    def test_bucket_classification(self):
        self.assertEqual(check.bucket("Chromium (Playwright)"), "optional")
        self.assertEqual(check.bucket("Optional imports"), "optional")
        self.assertEqual(check.bucket("API key works"), "key")
        self.assertEqual(check.bucket("Memory store"), "core")

    def test_exit_code_all_pass_is_zero(self):
        res = [(True, l, "", check.bucket(l)) for l, _f in check.CHECKS]
        self.assertEqual(check.verdict(res)["code"], 0)

    def test_exit_code_core_failure_is_one(self):
        res = [(False, "Memory store", "boom", "core")]
        self.assertEqual(check.verdict(res)["code"], 1)

    def test_exit_code_key_failure_is_two(self):
        res = [(False, "API key works", "no key", "key")]
        self.assertEqual(check.verdict(res)["code"], 2)

    def test_exit_code_optional_failure_is_still_zero(self):
        res = [(False, "Chromium (Playwright)", "missing", "optional")]
        self.assertEqual(check.verdict(res)["code"], 0)

    def test_core_failure_outranks_key_and_optional(self):
        res = [(False, "Memory store", "", "core"),
               (False, "API key works", "", "key"),
               (False, "Chromium (Playwright)", "", "optional")]
        self.assertEqual(check.verdict(res)["code"], 1)

    def test_capabilities_off_when_missing(self):
        res = self._res(
            (False, "API key works", ""),
            (False, "Chromium (Playwright)", ""),
            (False, "Optional imports", "none installed"),
            (True, "Memory store", "sqlite OK - 3 facts"),
        )
        lines = "\n".join(check.capability_lines(res))
        self.assertIn("skills-only", _row(lines, "AI chat"))
        self.assertIn("playwright install chromium",
                      _row(lines, "Browser skills"))
        self.assertIn("requirements-voice.txt",
                      _row(lines, "Voice input"))
        self.assertEqual(_row(lines, "Memory"), "sqlite OK - 3 facts")

    def test_capabilities_on_when_present(self):
        res = self._res(
            (True, "API key works", "key valid"),
            (True, "Chromium (Playwright)", "chromium OK"),
            (True, "Optional imports", "sounddevice, playwright"),
            (True, "Memory store", "sqlite OK - 3 facts"),
        )
        lines = "\n".join(check.capability_lines(res))
        self.assertEqual(_row(lines, "AI chat"), "on")
        self.assertEqual(_row(lines, "Voice input"), "on")
        self.assertEqual(_row(lines, "Browser skills"), "on")


if __name__ == "__main__":
    unittest.main()
