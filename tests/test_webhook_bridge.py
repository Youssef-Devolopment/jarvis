"""webhook_bridge — n8n inbound/outbound event bridge."""
from __future__ import annotations

import unittest
from unittest import mock

from skills import webhook_bridge as wb


def _prefs(enabled=True, token="", out_url=""):
    return lambda: (enabled, token, out_url)


class IngestTests(unittest.TestCase):
    def setUp(self):
        wb._recent.clear()
        wb._id = 0

    def test_disabled_is_403(self):
        with mock.patch.object(wb, "_prefs", _prefs(enabled=False)):
            body, code = wb.ingest({"text": "hi"}, None, "127.0.0.1")
        self.assertEqual(code, 403)
        self.assertIn("disabled", body["error"])

    def test_localhost_without_token_accepted(self):
        with mock.patch.object(wb, "_prefs", _prefs(token="")):
            body, code = wb.ingest({"event": "ci", "text": "build ok"},
                                   None, "127.0.0.1")
        self.assertEqual(code, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(wb.recent()[0]["event"], "ci")

    def test_no_token_rejects_remote_addr(self):
        with mock.patch.object(wb, "_prefs", _prefs(token="")):
            _, code = wb.ingest({"text": "x"}, None, "203.0.113.9")
        self.assertEqual(code, 403)

    def test_token_gate(self):
        with mock.patch.object(wb, "_prefs", _prefs(token="s3cret")):
            _, bad = wb.ingest({"text": "x"}, "wrong", "127.0.0.1")
            _, none = wb.ingest({"text": "x"}, None, "127.0.0.1")
            ok, good = wb.ingest({"text": "x"}, "s3cret", "127.0.0.1")
        self.assertEqual(bad, 401)
        self.assertEqual(none, 401)
        self.assertEqual(good, 200)
        self.assertTrue(ok["ok"])

    def test_run_dispatches_through_skills(self):
        with mock.patch.object(wb, "_prefs", _prefs(token="t")), \
             mock.patch("skills.dispatch",
                        return_value="skill said hi") as d:
            body, code = wb.ingest(
                {"text": "what time is it", "run": True}, "t", "127.0.0.1")
        d.assert_called_once_with("what time is it")
        self.assertEqual(body["ran"], "skill said hi")

    def test_run_survives_skill_crash(self):
        with mock.patch.object(wb, "_prefs", _prefs(token="t")), \
             mock.patch("skills.dispatch", side_effect=RuntimeError("boom")):
            body, code = wb.ingest(
                {"text": "x", "run": True}, "t", "127.0.0.1")
        self.assertEqual(code, 200)
        self.assertIn("error", body["ran"])

    def test_speak_toasts_and_talks(self):
        import sys
        import types
        fake_voice = types.ModuleType("voice")
        fake_voice.speak_async = mock.MagicMock()
        with mock.patch.object(wb, "_prefs", _prefs(token="t")), \
             mock.patch("system.notify.alert") as al, \
             mock.patch.dict(sys.modules, {"voice": fake_voice}):
            wb.ingest({"text": "timer done", "speak": True}, "t", "127.0.0.1")
        al.assert_called_once()
        fake_voice.speak_async.assert_called_once_with("timer done")

    def test_non_object_payload_rejected(self):
        with mock.patch.object(wb, "_prefs", _prefs(token="t")):
            _, code = wb.ingest(["not", "a", "dict"], "t", "127.0.0.1")
        self.assertEqual(code, 400)

    def test_payload_data_must_serialize(self):
        with mock.patch.object(wb, "_prefs", _prefs(token="t")):
            body, code = wb.ingest(
                {"event": "x", "data": object()}, "t", "127.0.0.1")
        self.assertEqual(code, 200)  # degrades to a string, never 500s


class OutboundTests(unittest.TestCase):
    def test_send_without_url_explains(self):
        with mock.patch.object(wb, "_prefs", _prefs(out_url="")):
            ok, msg = wb.send_now("hello")
        self.assertFalse(ok)
        self.assertIn("set n8n url", msg)

    def test_send_posts_json(self):
        seen = {}

        class _Resp:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def fake_urlopen(req, timeout=10):
            seen["url"] = req.full_url
            seen["body"] = req.data
            return _Resp()
        with mock.patch.object(wb, "_prefs",
                               _prefs(out_url="https://hook.example/x")), \
             mock.patch.object(wb.urllib.request, "urlopen",
                               side_effect=fake_urlopen):
            ok, msg = wb.send_now("build green")
        self.assertTrue(ok)
        self.assertIn("200", msg)
        self.assertEqual(seen["url"], "https://hook.example/x")
        self.assertIn(b"build green", seen["body"])

    def test_send_failure_is_reported_not_raised(self):
        with mock.patch.object(wb, "_prefs",
                               _prefs(out_url="https://hook.example/x")), \
             mock.patch.object(wb.urllib.request, "urlopen",
                               side_effect=OSError("refused")):
            ok, msg = wb.send_now("x")
        self.assertFalse(ok)
        self.assertIn("failed", msg)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        wb._recent.clear()
        wb._id = 0

    def test_in_and_recent_routes(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"app import failed: {exc}")
        client = app.test_client()
        with mock.patch.object(wb, "_prefs", _prefs(token="")):
            r = client.post("/api/webhook/in",
                            json={"event": "ping", "text": "hello"})
            self.assertEqual(r.status_code, 200)
            r2 = client.get("/api/webhook/recent")
        self.assertEqual(r2.status_code, 200)
        evs = r2.get_json()["events"]
        self.assertEqual(evs[0]["event"], "ping")

    def test_inbound_disabled_by_default(self):
        try:
            from server import app
        except Exception as exc:  # pragma: no cover
            self.skipTest(f"app import failed: {exc}")
        client = app.test_client()
        r = client.post("/api/webhook/in", json={"text": "x"})
        self.assertEqual(r.status_code, 403)


if __name__ == "__main__":
    unittest.main()
