"""memory.schema — PRAGMA user_version adoption, forward-only
migrations, pre-migration backups — plus memory.store.integrity()."""
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


class BackupTests(unittest.TestCase):
    """ensure() snapshots the DB to memory/backups/ before migrating."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db = Path(self._tmp.name) / "m.db"
        self.conn = sqlite3.connect(str(self.db))
        self.conn.execute("CREATE TABLE t (x INTEGER)")
        self.bdir = Path(self._tmp.name) / "backups"

    def tearDown(self):
        try:
            self.conn.close()
        except Exception:
            pass
        self._tmp.cleanup()

    def test_backup_created_before_migration(self):
        res = schema.ensure(self.conn)
        self.assertTrue(res["migrated"])
        self.assertIsNotNone(res["backup"])
        baks = list(self.bdir.glob("m.v*.db"))
        self.assertEqual(len(baks), 1)
        # snapshot is consistent and still shows the OLD version
        bconn = sqlite3.connect(str(baks[0]))
        try:
            ver = int(bconn.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(ver, 0)
            rows = bconn.execute("SELECT COUNT(*) FROM t").fetchone()
            self.assertEqual(rows[0], 0)
        finally:
            bconn.close()

    def test_no_new_backup_when_schema_already_current(self):
        schema.ensure(self.conn)          # migration → backup #1
        res = schema.ensure(self.conn)    # current → no backup
        self.assertFalse(res["migrated"])
        self.assertEqual(len(list(self.bdir.glob("m.v*.db"))), 1)

    def test_backup_failure_never_blocks_migration(self):
        with mock.patch.object(schema.sqlite3, "connect",
                               side_effect=RuntimeError("disk full")):
            res = schema.ensure(self.conn)
        self.assertTrue(res["ok"])
        self.assertTrue(res["migrated"])
        self.assertIsNone(res["backup"])
        self.assertEqual(
            int(self.conn.execute("PRAGMA user_version").fetchone()[0]),
            schema.SCHEMA_VERSION)

    def test_prune_keeps_only_newest_backups(self):
        self.bdir.mkdir(parents=True)
        for day in range(1, 6):
            (self.bdir / f"m.v0-2020010{day}-000000.db").touch()
        schema._prune(self.bdir, "m")
        left = sorted(p.name for p in self.bdir.glob("m.v*.db"))
        self.assertEqual(len(left), schema._BACKUP_KEEP)
        self.assertIn("20200105", left[-1])   # newest survives


class IntegrityTests(unittest.TestCase):
    """store.integrity() — PRAGMA integrity_check for the health probe."""

    def test_ok_on_the_real_store_db(self):
        from memory import store
        self.assertEqual(store.integrity(), "ok")

    def test_corrupt_db_reports_unreadable(self):
        from memory import store
        with tempfile.TemporaryDirectory() as tmp:
            garbage = Path(tmp) / "junk.db"
            garbage.write_bytes(b"this is definitely not a database")
            conn = sqlite3.connect(str(garbage))
            try:
                with mock.patch.object(store, "_get_conn",
                                       return_value=conn):
                    res = store.integrity()
            finally:
                conn.close()
        self.assertTrue(res.startswith("unreadable"), res)

    def test_integrity_never_raises(self):
        from memory import store
        with mock.patch.object(store, "_get_conn",
                               side_effect=RuntimeError("db gone")):
            res = store.integrity()
        self.assertTrue(res.startswith("unreadable"), res)


if __name__ == "__main__":
    unittest.main()
