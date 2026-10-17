"""v1.30.0 — review-fix batch: WAL, thread-crash hook, LAN token
gate, dependency lockfile. All four were verified gaps, not
remodels: one pragma, one hook, one gate, one freeze."""
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


class WalModeTests(unittest.TestCase):
    def setUp(self):
        import memory.prefs as prefs
        import memory.store as st
        self.st = st
        self.prefs = prefs
        self._real_db = st._DB_PATH
        self._real_conn = st._conn
        self._real_prefdb = prefs._DB
        self.tmp = Path(tempfile.mkdtemp())
        st._DB_PATH = self.tmp / "t.db"
        st._conn = None
        prefs._DB = self.tmp / "p.db"
        self.addCleanup(self._restore)

    def _restore(self):
        self.st._DB_PATH = self._real_db
        try:
            if self.st._conn is not None:
                self.st._conn.close()
        except Exception:
            pass
        self.st._conn = self._real_conn
        self.prefs._DB = self._real_prefdb

    def _mode(self, path):
        c = sqlite3.connect(str(path))
        try:
            return c.execute("PRAGMA journal_mode").fetchone()[0].lower()
        finally:
            c.close()

    def test_store_writes_enable_wal(self):
        self.st.save_message("s", "user", "hello wal")
        self.assertEqual(self._mode(self.tmp / "t.db"), "wal")

    def test_prefs_writes_enable_wal(self):
        self.assertTrue(self.prefs.set_pref("dnd", True))
        self.assertEqual(self._mode(self.tmp / "p.db"), "wal")

    def test_ensure_wal_never_raises(self):
        from memory.schema import ensure_wal
        c = sqlite3.connect(":memory:")
        c.close()
        self.assertEqual(ensure_wal(c), "")
        self.assertEqual(ensure_wal(None), "")


class ThreadHookTests(unittest.TestCase):
    def _args(self):
        try:
            raise RuntimeError("boom in background")
        except RuntimeError:
            import sys
            t, v, b = sys.exc_info()
        return SimpleNamespace(thread="worker-1", exc_type=t,
                               exc_value=v, exc_traceback=b)

    def test_unhandled_thread_exception_reaches_logs(self):
        import logger
        logger.setup_logging("INFO")
        self.assertTrue(callable(threading.excepthook))
        with self.assertLogs("thread-crash", level="ERROR") as cm:
            threading.excepthook(self._args())
        self.assertTrue(any("worker-1" in m for m in cm.output))

    def test_setup_logging_idempotent(self):
        import logger
        hook = threading.excepthook
        logger.setup_logging("INFO")
        logger.setup_logging("DEBUG")
        self.assertIs(threading.excepthook, hook)


class LanAuthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from server import app
        except Exception as exc:
            raise unittest.SkipTest(f"app import failed: {exc}")
        cls.app = app
        cls.app.testing = True
        cls.client = app.test_client()

    LAN = {"REMOTE_ADDR": "192.168.1.50"}

    def _post(self, text, remote=None, token=None):
        headers = {}
        if token is not None:
            headers["X-Jarvis-Token"] = token
        return self.client.post("/api/command", json={"text": text},
                                headers=headers,
                                environ_overrides=remote or {})

    def test_lan_write_without_token_is_forbidden(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("JARVIS_TOKEN", None)
            r = self._post("hello there", remote=self.LAN)
        self.assertEqual(r.status_code, 403)
        self.assertIn("JARVIS_TOKEN", r.get_data(as_text=True))

    def test_lan_write_with_wrong_token_is_unauthorized(self):
        with mock.patch.dict(os.environ, {"JARVIS_TOKEN": "right"}):
            r = self._post("hello there", remote=self.LAN,
                           token="wrong")
        self.assertEqual(r.status_code, 401)

    def test_lan_write_with_token_passes_through(self):
        from errors import ConfigError
        with mock.patch.dict(os.environ, {"JARVIS_TOKEN": "right"}), \
                mock.patch("routes.api.get_client",
                           side_effect=ConfigError("no key")):
            r = self._post("hello there", remote=self.LAN,
                           token="right")
        self.assertEqual(r.status_code, 200)
        self.assertIn("no_key", r.get_data(as_text=True))

    def test_loopback_needs_no_token(self):
        from errors import ConfigError
        with mock.patch.dict(os.environ):
            os.environ.pop("JARVIS_TOKEN", None)
            with mock.patch("routes.api.get_client",
                             side_effect=ConfigError("no key")):
                r = self._post("hello there")
        self.assertEqual(r.status_code, 200)

    def test_lan_reads_stay_open(self):
        with mock.patch.dict(os.environ):
            os.environ.pop("JARVIS_TOKEN", None)
            r = self.client.get("/api/info",
                                environ_overrides=self.LAN)
        self.assertEqual(r.status_code, 200)

    def test_lan_write_wrong_same_length_token_rejected(self):
        with mock.patch.dict(os.environ, {"JARVIS_TOKEN": "abcd"}):
            r = self._post("hello there", remote=self.LAN, token="abce")
        self.assertEqual(r.status_code, 401)

    def test_lan_write_non_ascii_token_no_crash(self):
        # hmac.compare_digest on encoded bytes must not 500 on non-ASCII.
        with mock.patch.dict(os.environ, {"JARVIS_TOKEN": "sécrèt"}):
            r = self._post("hello there", remote=self.LAN,
                           token="different")
        self.assertEqual(r.status_code, 401)


class LockfileTests(unittest.TestCase):
    def test_lockfile_pins_core_deps(self):
        text = (ROOT / "requirements-lock.txt").read_text(
            encoding="utf-8")
        self.assertIn("Regenerate:", text)
        for dep in ("Flask==", "openai==", "mcp=="):
            self.assertIn(dep, text)


if __name__ == "__main__":
    unittest.main()
