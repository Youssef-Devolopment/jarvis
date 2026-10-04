"""Tidy engine: old temp files found, removed only on confirm."""
from __future__ import annotations

import os
import time
import unittest
from pathlib import Path
from tempfile import mkdtemp

from system import tidy


class _TempHome:
    """Redirect TEMP/TMP at a scratch dir AND pin the dir list —
    otherwise C:\\Windows\\Temp leaks the host's files into tests."""

    def __init__(self, root):
        self.root = root

    def __enter__(self):
        from system import tidy
        self._old = {k: os.environ.get(k) for k in ("TEMP", "TMP")}
        os.environ["TEMP"] = self.root
        os.environ["TMP"] = self.root
        self._dirs = tidy._temp_dirs
        tidy._temp_dirs = lambda: [Path(self.root)]
        return self

    def __exit__(self, *exc):
        from system import tidy
        for k, v in self._old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        tidy._temp_dirs = self._dirs
        return False


def _aged(path, days):
    ts = time.time() - days * 86400
    os.utime(path, (ts, ts))


class TidyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = mkdtemp()

    def test_scan_finds_only_old_files(self):
        old = Path(self.tmp) / "old.tmp"
        new = Path(self.tmp) / "new.tmp"
        old.write_bytes(b"x" * 100)
        new.write_bytes(b"y" * 100)
        _aged(str(old), 8)
        with _TempHome(self.tmp):
            r = tidy.scan()
        self.assertEqual(r["stale_files"], 1)
        self.assertTrue(r["paths"][0].endswith("old.tmp"))

    def test_dry_run_removes_nothing(self):
        old = Path(self.tmp) / "old.tmp"
        old.write_bytes(b"x" * 200000)
        _aged(str(old), 8)
        with _TempHome(self.tmp):
            r = tidy.clean(dry_run=True)
        self.assertEqual(r["removed"], 0)
        self.assertTrue(old.exists())
        self.assertGreater(r["stale_mb"], 0)

    def test_clean_removes_old_keeps_new(self):
        old = Path(self.tmp) / "old.tmp"
        new = Path(self.tmp) / "new.tmp"
        old.write_bytes(b"x" * 100)
        new.write_bytes(b"y" * 100)
        _aged(str(old), 8)
        with _TempHome(self.tmp):
            r = tidy.clean(dry_run=False)
        self.assertEqual(r["removed"], 1)
        self.assertFalse(old.exists())
        self.assertTrue(new.exists())

    def test_prune_keeps_newest_reports(self):
        from ai import dream_mode
        rep = Path(mkdtemp())
        for i in range(35):
            f = rep / f"dream_202001{i:02d}.json"
            f.write_text("{}")
            _aged(str(f), 40 - i)
        real = dream_mode._REPORTS
        dream_mode._REPORTS = rep
        try:
            r = tidy.prune_dream_reports(keep=30)
        finally:
            dream_mode._REPORTS = real
        self.assertEqual(r["pruned"], 5)
        self.assertEqual(len(list(rep.glob("*.json"))), 30)

    def test_skill_patterns(self):
        import re
        from skills.tidy_skill import TIDY_PATTERNS
        for good in ["tidy", "tidy up", "clean temp files",
                     "clean the temp", "clear temporary files"]:
            self.assertTrue(
                any(re.match(p, good, re.IGNORECASE)
                    for p in TIDY_PATTERNS), good)
        for bad in ["tidy confirm", "clean notes", "temperature"]:
            self.assertFalse(
                any(re.match(p, bad, re.IGNORECASE)
                    for p in TIDY_PATTERNS), bad)


if __name__ == "__main__":
    unittest.main()
