"""memory.schema — PRAGMA user_version adoption + forward-only migrations."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from memory import schema


class EnsureTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "m.db"
        self.conn = sqlite3.connect(str(self.db))
        self.conn.execute("CREATE TABLE t (x INTEGER)")

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def _user_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def test_fresh_db_adopts_current_version(self):
        self.assertEqual(self._user_version(), 0)
        res = schema.ensure(self.conn)
        self.assertTrue(res["ok"])
        self.assertTrue(res["migrated"])
        self.assertEqual(self._user_version(), schema.SCHEMA_VERSION)

    def test_ensure_is_idempotent(self):
        schema.ensure(self.conn)
        res = schema.ensure(self.conn)
        self.assertTrue(res["ok"])
        self.assertFalse(res["migrated"])
        self.assertEqual(self._user_version(), schema.SCHEMA_VERSION)

    def test_newer_db_is_left_untouched(self):
        newer = schema.SCHEMA_VERSION + 5
        self.conn.execute(f"PRAGMA user_version = {newer}")
        res = schema.ensure(self.conn)
        self.assertFalse(res["ok"])
        self.assertIn("newer", res["detail"])
        self.assertEqual(self._user_version(), newer)

    def test_migration_steps_run_in_order_from_stored_version(self):
        ran = []
        with mock.patch.object(schema, "SCHEMA_VERSION", 4), \
             mock.patch.dict(schema._MIGRATIONS,
                             {2: lambda c: ran.append(2),
                              3: lambda c: ran.append(3),
                              4: lambda c: ran.append(4)}):
            self.conn.execute("PRAGMA user_version = 1")
            res = schema.ensure(self.conn)
        self.assertTrue(res["ok"])
        self.assertEqual(ran, [2, 3, 4])
        self.assertEqual(self._user_version(), 4)

    def test_missing_migration_entry_is_skipped(self):
        with mock.patch.object(schema, "SCHEMA_VERSION", 2):
            self.conn.execute("PRAGMA user_version = 1")
            res = schema.ensure(self.conn)
        self.assertTrue(res["ok"])  # no step for v2 yet — still versions it
        self.assertEqual(self._user_version(), 2)


class StatusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "s.db"

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_reports_new_database(self):
        res = schema.status(self.db)
        self.assertTrue(res["ok"])
        self.assertFalse(res["exists"])

    def test_unversioned_file_is_pending(self):
        conn = sqlite3.connect(str(self.db))
        conn.execute("CREATE TABLE t (x)")
        conn.commit()
        conn.close()
        res = schema.status(self.db)
        self.assertTrue(res["ok"])
        self.assertTrue(res.get("pending"))

    def test_current_version_reports_current(self):
        conn = sqlite3.connect(str(self.db))
        conn.execute("CREATE TABLE t (x)")
        conn.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION}")
        conn.commit()
        conn.close()
        res = schema.status(self.db)
        self.assertTrue(res["ok"])
        self.assertFalse(res.get("pending", False))
        self.assertIn("current", res["detail"])

    def test_newer_version_fails_safely(self):
        conn = sqlite3.connect(str(self.db))
        conn.execute("CREATE TABLE t (x)")
        conn.execute(f"PRAGMA user_version = {schema.SCHEMA_VERSION + 9}")
        conn.commit()
        conn.close()
        res = schema.status(self.db)
        self.assertFalse(res["ok"])
        self.assertIn("newer", res["detail"])


if __name__ == "__main__":
    unittest.main()
