"""Memory: dedup, supersede, ranked recall. Uses a scratch DB."""
import tempfile
import unittest
from pathlib import Path

import memory.store as st

_REAL_DB = st._DB_PATH


class MemoryTest(unittest.TestCase):
    def setUp(self):
        st._DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
        st._conn = None

    def tearDown(self):
        st._DB_PATH = _REAL_DB
        st._conn = None

    def test_remember_and_recall(self):
        i = st.remember("User name is Youssef", "identity", "test")
        self.assertGreater(i, 0)
        r = st.recall("youssef")
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["fact"], "User name is Youssef")

    def test_duplicate_skipped(self):
        a = st.remember("User name is Youssef", "identity", "test")
        b = st.remember("User name is Youssef", "identity", "test")
        self.assertEqual(a, b)
        self.assertEqual(len(st.recall("")), 1)

    def test_supersede_hides_old(self):
        st.remember("User favorite food is pizza", "food", "test")
        st.remember("User favorite food is pasta and pizza", "food", "test")
        hits = st.recall("pizza")
        self.assertEqual(len(hits), 1)
        self.assertIn("pasta", hits[0]["fact"])

    def test_multiword_recall(self):
        st.remember("User name is Youssef", "identity", "test")
        st.remember("Jarvis project uses Flask", "project", "test")
        r = st.recall("youssef name")
        self.assertTrue(any("Youssef" in x["fact"] for x in r))

    def test_ranking_prefers_relevant(self):
        st.remember("User likes tea", "food", "test")
        st.remember("Jarvis project uses Flask and DeepSeek", "project", "test")
        r = st.recall("flask project")
        self.assertTrue(r)
        self.assertIn("Flask", r[0]["fact"])

    def test_forget(self):
        st.remember("Temporary fact xyz", "general", "test")
        self.assertEqual(st.forget("xyz"), 1)
        self.assertEqual(st.recall("xyz"), [])

    def test_status_index_exists(self):
        c = st._get_conn()
        names = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
        self.assertIn("idx_facts_status_id", names)

    def test_count_matches_all_facts(self):
        st.remember("Count me once", "general", "test")
        st.remember("Count me twice", "general", "test")
        self.assertEqual(st.count_facts(), len(st.all_facts(limit=10000)))
        self.assertEqual(st.count_facts(), 2)

    def test_recall_parity_at_scale(self):
        c = st._get_conn()
        c.executemany(
            "INSERT INTO facts (fact, category, created_at) VALUES "
            "(?, ?, datetime('now'))",
            [(f"bulk fact {i} tungsten carbide", "bulk")
             for i in range(2000)])
        c.commit()
        before = [f["fact"] for f in st.recall("tungsten")]
        self.assertTrue(before)
        self.assertEqual(st.count_facts(), 2000)
        after = [f["fact"] for f in st.recall("tungsten")]
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
