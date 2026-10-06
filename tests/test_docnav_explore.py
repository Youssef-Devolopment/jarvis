"""doc_navigator + multi_search — Deep Web Intelligence suite."""
from __future__ import annotations

import unittest
from unittest import mock

from skills import doc_navigator as dn
from skills import multi_search as ms


class DocNavigatorTests(unittest.TestCase):
    def test_clean_strips_markup_and_code(self):
        body = "# Title\nSome **bold** text\n```py\nrun()\n`````\ndone"
        out = dn._clean(body)
        self.assertNotIn("```", out)
        self.assertNotIn("**", out)
        self.assertIn("done", out)

    def test_gather_prefers_pypi_for_plain_names(self):
        with mock.patch.object(dn, "_pypi",
                               return_value={"summary": "s", "body": "b",
                                             "url": "u", "source": "PyPI"}) as p, \
             mock.patch.object(dn, "_github") as g:
            out = dn.gather("flask")
        p.assert_called_once_with("flask")
        g.assert_not_called()
        self.assertEqual(out["source"], "PyPI")

    def test_gather_uses_github_for_slugs(self):
        doc = {"summary": "", "body": "readme", "url": "u",
               "source": "GitHub"}
        with mock.patch.object(dn, "_github", return_value=doc) as g:
            out = dn.gather("Youssef-Devolopment/jarvis")
        g.assert_called_once()
        self.assertEqual(out["source"], "GitHub")

    def test_brief_returns_none_when_llm_broken(self):
        with mock.patch("ai.client.get_client",
                        side_effect=RuntimeError("no key")):
            self.assertIsNone(dn._brief("x", {"body": "text"}))

    def test_skill_falls_back_to_extractive(self):
        doc = {"summary": "A micro web framework.", "body": "Flask body…",
               "url": "https://flask.palletsprojects.com/",
               "source": "PyPI"}
        with mock.patch.object(dn, "gather", return_value=doc), \
             mock.patch.object(dn, "_brief", return_value=None):
            out = dn.skill_docs("docs for flask", mock.MagicMock(
                group=lambda k: "flask"))
        self.assertIn("A micro web framework.", out)
        self.assertIn("Source: https://flask", out)

    def test_skill_no_docs_message(self):
        with mock.patch.object(dn, "gather", return_value=None):
            out = dn.skill_docs("docs for zzznotapackage", mock.MagicMock(
                group=lambda k: "zzznotapackage"))
        self.assertIn("No docs found", out)

    def test_skill_registered(self):
        from skills import dispatch
        with mock.patch.object(dn, "gather", return_value=None):
            out = dispatch("docs for definitelynotalib")
        self.assertIsInstance(out, str)
        self.assertIn("No docs found", out)


class MultiSearchTests(unittest.TestCase):
    def test_variants_cover_the_bases(self):
        v = ms._variants("vector databases")
        self.assertEqual(len(v), 4)
        self.assertEqual(v[0], "vector databases")
        self.assertIn("examples", v[2])

    def test_explore_dedupes_by_url(self):
        a = [{"title": "A", "url": "https://x/1", "snippet": "long " * 30},
             {"title": "A dup", "url": "https://x/1/", "snippet": ""}]
        b = [{"title": "B", "url": "https://y/2", "snippet": "short"},
             {"title": "C", "url": "https://z/3", "snippet": "mid"}]
        calls = {"n": 0}

        def fake_search(q):
            calls["n"] += 1
            return a if calls["n"] % 2 else b

        hits, queries = ms.explore("topic", search_fn=fake_search)
        self.assertEqual(queries, 4)
        self.assertEqual(len(hits), 3)  # dup URL collapsed
        urls = [h["url"] for h in hits]
        self.assertIn("https://x/1", urls)

    def test_synthesize_none_when_llm_broken(self):
        with mock.patch("ai.client.get_client",
                        side_effect=RuntimeError("no key")):
            self.assertIsNone(ms._synthesize("t", [{"title": "a",
                                                    "url": "u"}]))

    def test_skill_falls_back_to_top_results(self):
        hits = [{"title": "One", "url": "https://one", "snippet": "s"},
                {"title": "Two", "url": "https://two", "snippet": "s"}]
        with mock.patch.object(ms, "explore", return_value=(hits, 4)), \
             mock.patch.object(ms, "_synthesize", return_value=None):
            out = ms.skill_explore(
                "explore vector databases",
                mock.MagicMock(group=lambda k: "vector databases"))
        self.assertIn("4 queries", out)
        self.assertIn("https://one", out)

    def test_skill_registered(self):
        from skills import dispatch
        with mock.patch.object(ms, "explore", return_value=([], 4)):
            out = dispatch("explore quantum tea kettles")
        self.assertIsInstance(out, str)
        self.assertIn("No results", out)

    def test_search_failure_in_one_variant_is_survived(self):
        def flaky(q):
            if "guide" in q:
                raise OSError("tier down")
            return [{"title": q, "url": f"https://s/{abs(hash(q))%9999}",
                     "snippet": "ok"}]
        hits, queries = ms.explore("anything", search_fn=flaky)
        self.assertEqual(queries, 4)
        self.assertGreaterEqual(len(hits), 3)


if __name__ == "__main__":
    unittest.main()
