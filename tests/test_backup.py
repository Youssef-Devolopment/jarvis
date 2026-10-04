"""Backup: zips memory DB + .env into tmp, prunes, lists."""
from __future__ import annotations

import re
import tempfile
import unittest
import zipfile
from pathlib import Path

from system import backup as B
from skills.backup_skill import BACKUP_PATTERNS


def _root_with(files: dict) -> Path:
    root = Path(tempfile.mkdtemp())
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content)
    return root


class BackupTests(unittest.TestCase):
    def test_creates_zip_with_both_files(self):
        root = _root_with({"memory/jarvis_memory.db": b"DB" * 100,
                           ".env": b"KEY=x"})
        dest = Path(tempfile.mkdtemp())
        res = B.create_backup(root=root, backup_dir=dest)
        self.assertTrue(res["ok"])
        self.assertEqual(len(res["files"]), 2)
        self.assertGreater(res["kb"], 0)
        names = zipfile.ZipFile(res["path"]).namelist()
        self.assertIn("memory/jarvis_memory.db", names)
        self.assertIn(".env", names)

    def test_missing_everything_errors(self):
        root = _root_with({})
        res = B.create_backup(root=root,
                              backup_dir=Path(tempfile.mkdtemp()))
        self.assertFalse(res["ok"])

    def test_prunes_to_keep(self):
        root = _root_with({".env": b"KEY=x"})
        dest = Path(tempfile.mkdtemp())
        for i in range(7):
            (dest / f"jarvis-backup-2020010{i}.zip").write_bytes(b"z")
        res = B.create_backup(root=root, backup_dir=dest, keep=5)
        self.assertTrue(res["ok"])
        left = list(dest.glob("jarvis-backup-*.zip"))
        self.assertEqual(len(left), 5)

    def test_list_backups(self):
        dest = Path(tempfile.mkdtemp())
        (dest / "jarvis-backup-20200101.zip").write_bytes(b"z" * 2048)
        items = B.list_backups(backup_dir=dest)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["kb"], 2.0)

    def test_patterns(self):
        for good in ["backup", "back up", "backup memory",
                     "back up everything", "backup jarvis"]:
            self.assertTrue(any(re.match(p, good, re.IGNORECASE)
                                for p in BACKUP_PATTERNS), good)


class BackupApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_backups_list_shape(self):
        r = self.__class__.client.get("/api/backups")
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertIn("count", d)
        self.assertIn("backups", d)


if __name__ == "__main__":
    unittest.main()
