"""Deep research: search/filter/fetch/synthesize/report/jobs —
all I/O faked, memory on a scratch DB, reports in tmp."""
from __future__ import annotations

import re
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import memory.store as st
from system import research_agent as ra
from skills.deep_research import RESEARCH_PATTERNS

_FAKE_RESULTS = [
    {"title": "A", "url": "https://a.example/x", "snippet": "s1"},
    {"title": "A dup", "url": "https://a.example/x", "snippet": "s1"},
    {"title": "B", "url": "https://b.example/y", "snippet": "s2"},
    {"title": "C", "url": "ftp://c.example/z", "snippet": "s3"},
    {"title": "D", "url": "https://d.example/w", "snippet": "s4"},
]

_FAKE_HTML = """<html><head><title>Page A</title></head><body>
<nav>menu noise</nav><div class="ad-banner">buy now</div>
<p>First paragraph about widgets and sprockets.</p>
<pre><code>def hello():
    return "world"</code></pre>
<p>Second paragraph with more detail here.</p>
<pre>print("no code tag")</pre>
</body></html>"""

_SUB_HTML = """<html><head><title>Sub</title></head><body>
<p>Subpage detail line.</p>
<a href="/other">other</a>
</body></html>"""


def _raw(url):
    if url == "https://a.example/x":
        return _FAKE_HTML.replace(
            "</body>",
            '<a href="https://a.example/sub">sub</a></body>')
    if url == "https://a.example/sub":
        return _SUB_HTML
    raise RuntimeError("unreachable " + url)


class SearchTests(unittest.TestCase):
    def test_dedupes_skips_nonhttp_and_caps(self):
        out = ra.search_sources("t", k=2,
                                search_fn=lambda q: _FAKE_RESULTS)
        self.assertEqual([r["url"] for r in out],
                         ["https://a.example/x", "https://b.example/y"])

    def test_search_failure_gives_empty(self):
        def boom(q):
            raise RuntimeError("down")
        self.assertEqual(ra.search_sources("t", search_fn=boom), [])


class FetchTests(unittest.TestCase):
    def test_text_clean_code_kept(self):
        f = ra.fetch_source("https://a.example/x", depth=0, raw_fn=_raw)
        self.assertEqual(f["title"], "Page A")
        self.assertNotIn("buy now", f["text"])
        self.assertNotIn("menu noise", f["text"])
        self.assertIn("widgets and sprockets", f["text"])
        self.assertEqual(len(f["code"]), 2)
        self.assertIn("def hello", f["code"][0])

    def test_same_host_recursion_merges(self):
        f = ra.fetch_source("https://a.example/x", raw_fn=_raw)
        self.assertGreaterEqual(f["subpages"], 1)
        self.assertIn("Subpage detail", f["text"])

    def test_bad_scheme_and_failure(self):
        self.assertEqual(ra.fetch_source("ftp://x").get("text"), "")
        self.assertEqual(
            ra.fetch_source("https://x", raw_fn=lambda u: None).get("text"),
            "")


class SynthTests(unittest.TestCase):
    _srcs = [{"title": "A", "url": "https://a.example",
              "text": "Alpha line one.\nMore alpha."},
             {"title": "B", "url": "https://b.example",
              "text": "Beta line one.\nMore beta."}]

    def test_llm_path_parses(self):
        llm = lambda t, d: "TL;DR: Things work.\n- point one\n- point two"
        tldr, points = ra.synthesize("t", self._srcs, llm_fn=llm)
        self.assertEqual(tldr, "Things work.")
        self.assertEqual(points, ["point one", "point two"])

    def test_extractive_fallback_needs_no_key(self):
        tldr, points = ra.synthesize(
            "t", self._srcs, llm_fn=lambda t, d: None)
        self.assertIn("offline digest", tldr)
        self.assertEqual(len(points), 2)

    def test_empty_sources(self):
        tldr, points = ra.synthesize("t", [], llm_fn=lambda t, d: None)
        self.assertIn("No readable sources", tldr)
        self.assertEqual(points, [])


class ReportTests(unittest.TestCase):
    def test_markdown_shape(self):
        tmp = Path(tempfile.mkdtemp())
        fp = ra.write_report(
            "Quantum Dots", "Dots glow.", ["small", "bright"],
            [{"title": "A", "url": "https://a.example",
              "text": "body text here", "code": ["x = 1"]}],
            out_dir=tmp)
        self.assertTrue(str(fp).endswith("-quantum-dots.md"))
        md = fp.read_text(encoding="utf-8")
        for needle in ["# Research: Quantum Dots", "## TL;DR",
                       "Dots glow.", "- small", "```", "x = 1",
                       "https://a.example", "## Links"]:
            self.assertIn(needle, md)


class LoopTests(unittest.TestCase):
    def setUp(self):
        self._db = st._DB_PATH
        st._DB_PATH = Path(tempfile.mkdtemp()) / "t.db"
        st._conn = None
        self.tmp = Path(tempfile.mkdtemp())
        # _run_job alerts on completion — never pop real toasts in tests
        patcher = mock.patch("system.notify.alert")
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        st._DB_PATH = self._db
        st._conn = None

    def test_full_loop_offline(self):
        res = ra.research_topic(
            "widgets", out_dir=self.tmp, max_sources=2,
            search_fn=lambda q: _FAKE_RESULTS,
            fetch_fn=lambda u: {"url": u, "title": "T",
                                "text": "Some text about widgets." * 5,
                                "code": ["a = 1"]},
            llm_fn=lambda t, d: None)
        self.assertTrue(res["ok"])
        self.assertTrue(Path(res["path"]).exists())
        self.assertEqual(res["sources"], 2)
        hits = st.recall("widgets")
        self.assertTrue(any("Research on widgets" in h["fact"]
                           for h in hits))

    def test_empty_search_errors(self):
        res = ra.research_topic("x", out_dir=self.tmp,
                                search_fn=lambda q: [])
        self.assertFalse(res["ok"])

    def test_unreadable_errors(self):
        res = ra.research_topic(
            "x", out_dir=self.tmp,
            search_fn=lambda q: [{"title": "A", "url": "https://a.e"}],
            fetch_fn=lambda u: {"url": u, "title": "T",
                                "text": "", "code": []},
            llm_fn=lambda t, d: None)
        self.assertFalse(res["ok"])

    def test_jobs_lifecycle(self):
        with mock.patch.object(ra, "research_topic",
                               return_value={"ok": True, "path": "p"}):
            job = ra.start_research("x")
            self.assertEqual(job["status"], "running")
            for _ in range(100):
                st_ = ra.job_status(job["id"])
                if st_ and st_["status"] == "done":
                    break
                time.sleep(0.05)
            self.assertEqual(st_["result"], {"ok": True, "path": "p"})
        self.assertIsNone(ra.job_status("nope" * 3))

    def test_finished_jobs_pruned(self):
        with ra._jobs_lock:
            ra._jobs.clear()
            for i in range(25):
                ra._jobs[f"old{i}"] = {"id": f"old{i}", "topic": "t",
                                       "status": "done", "started": i,
                                       "result": None}
            ra._jobs["live"] = {"id": "live", "topic": "t",
                                "status": "running",
                                "started": 1000.0, "result": None}
        with mock.patch.object(ra, "research_topic",
                               return_value={"ok": True}):
            ra.start_research("new")
        with ra._jobs_lock:
            self.assertLessEqual(len(ra._jobs), ra._MAX_JOBS + 2)
            self.assertIn("live", ra._jobs)  # running never pruned
            self.assertNotIn("old0", ra._jobs)  # oldest pruned first
            ra._jobs.clear()


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from server import create_app
        cls.client = create_app().test_client()

    def test_post_starts_job(self):
        with mock.patch.object(ra, "start_research",
                               return_value={"id": "abc", "topic": "x",
                                             "status": "running"}):
            r = self.__class__.client.post("/api/research",
                                           json={"topic": "quantum"})
        self.assertEqual(r.status_code, 200)
        d = r.get_json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["id"], "abc")

    def test_post_missing_topic_400(self):
        r = self.__class__.client.post("/api/research", json={})
        self.assertEqual(r.status_code, 400)

    def test_poll_unknown_404(self):
        r = self.__class__.client.get("/api/research/zzz")
        self.assertEqual(r.status_code, 404)


class PatternTests(unittest.TestCase):
    def _match(self, text):
        for p in RESEARCH_PATTERNS:
            m = re.match(p, text, re.IGNORECASE)
            if m:
                return m.group("topic")
        return None

    def test_matches(self):
        self.assertEqual(self._match("research quantum dots"),
                         "quantum dots")
        self.assertEqual(self._match("deep research rust async"),
                         "rust async")
        self.assertEqual(self._match("investigate slow boot"), "slow boot")

    def test_no_bare_trigger(self):
        self.assertIsNone(self._match("research"))


if __name__ == "__main__":
    unittest.main()
