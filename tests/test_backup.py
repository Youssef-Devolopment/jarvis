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

    def test_restore_preview_needs_confirm(self):
        r = self.__class__.client.post("/api/backup/restore", json={})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d.get("needs_confirm"))
        self.assertIn("backups", d)

    def test_restore_missing_backup_400_no_side_effects(self):
        client = self.__class__.client
        r = client.post("/api/backup/restore",
                        json={"confirm": True, "file": "nope.zip"})
        self.assertEqual(r.status_code, 400)
        r = client.post("/api/backup/restore",
                        json={"confirm": True,
                              "file": "jarvis-backup-19990101-0000.zip"})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(r.get_json().get("ok"))


class RestoreTests(unittest.TestCase):
    def test_preview_needs_confirm(self):
        dest = Path(tempfile.mkdtemp())
        root = _root_with({"memory/jarvis_memory.db": b"DB",
                           ".env": b"KEY=x"})
        self.assertTrue(B.create_backup(root=root, backup_dir=dest)["ok"])
        res = B.restore_backup(backup_dir=dest)
        self.assertTrue(res["needs_confirm"])
        self.assertEqual(len(res["backups"]), 1)
        self.assertTrue(res["newest"].startswith("jarvis-backup-"))

    def test_roundtrip_restores_old_content(self):
        root = _root_with({"memory/jarvis_memory.db": b"OLD",
                           ".env": b"OLDKEY=1"})
        dest = Path(tempfile.mkdtemp())
        self.assertTrue(B.create_backup(root=root, backup_dir=dest)["ok"])
        (root / "memory/jarvis_memory.db").write_bytes(b"NEW")
        (root / ".env").write_bytes(b"NEWKEY=2")
        closed = []
        res = B.restore_backup(confirm=True, root=root, backup_dir=dest,
                               close_db=lambda: closed.append(1))
        self.assertTrue(res["ok"], res)
        self.assertEqual(sorted(res["restored"]),
                         [".env", "memory/jarvis_memory.db"])
        self.assertEqual((root / "memory/jarvis_memory.db").read_bytes(),
                         b"OLD")
        self.assertEqual((root / ".env").read_bytes(), b"OLDKEY=1")
        self.assertEqual(closed, [1])          # live handle released
        self.assertTrue(res["safety_backup"])  # pre-restore snapshot
        self.assertTrue(Path(res["safety_backup"]).is_file())

    def test_invalid_names_refused_before_anything_happens(self):
        dest = Path(tempfile.mkdtemp())
        root = _root_with({"memory/jarvis_memory.db": b"DB"})
        for bad in ("../evil.zip", "C:\\x\\b.zip", "other.zip",
                    "..\\jarvis-backup-x.zip"):
            res = B.restore_backup(bad, confirm=True, root=root,
                                   backup_dir=dest,
                                   close_db=lambda: None)
            self.assertFalse(res["ok"], bad)
        # nothing was written, no safety zips created
        self.assertEqual(list(dest.glob("*.zip")), [])
        self.assertEqual((root / "memory/jarvis_memory.db").read_bytes(),
                         b"DB")

    def test_confirm_without_backups_errors(self):
        res = B.restore_backup(confirm=True,
                               root=_root_with({"memory/jarvis_memory.db":
                                                b"DB"}),
                               backup_dir=Path(tempfile.mkdtemp()))
        self.assertFalse(res["ok"])
        self.assertIn("no backups", res["error"])

    def test_zip_slip_refused(self):
        dest = Path(tempfile.mkdtemp())
        evil = dest / "jarvis-backup-evil.zip"
        with zipfile.ZipFile(evil, "w") as z:
            z.writestr("../evil.txt", "pwned")
        root = _root_with({"memory/jarvis_memory.db": b"DB"})
        res = B.restore_backup(evil.name, confirm=True, root=root,
                               backup_dir=dest, close_db=lambda: None)
        self.assertFalse(res["ok"])
        self.assertIn("unsafe", res["error"])
        self.assertFalse((dest.parent / "evil.txt").exists())

    def test_zip_without_restorable_files_errors(self):
        dest = Path(tempfile.mkdtemp())
        fp = dest / "jarvis-backup-empty.zip"
        with zipfile.ZipFile(fp, "w") as z:
            z.writestr("docs/readme.txt", "hi")
        res = B.restore_backup(fp.name, confirm=True,
                               root=_root_with({"memory/jarvis_memory.db":
                                                b"DB"}),
                               backup_dir=dest, close_db=lambda: None)
        self.assertFalse(res["ok"])

    def test_restore_patterns(self):
        from skills.backup_skill import RESTORE_PATTERNS
        for good in ("restore", "restore backup", "restore my backup",
                     "recover", "restore confirm", "restore backup confirm",
                     "recover confirm", "restore memory"):
            self.assertTrue(
                any(re.match(p, good, re.IGNORECASE)
                    for p in RESTORE_PATTERNS), good)
        for bad in ("restore layout home", "restored", "undo restore",
                    "restore confirm later"):
            self.assertFalse(
                any(re.match(p, bad, re.IGNORECASE)
                    for p in RESTORE_PATTERNS), bad)


if __name__ == "__main__":
    unittest.main()
