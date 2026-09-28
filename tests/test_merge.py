"""Merge regressions: unified skills registered once, dupes gone."""
import unittest

from skills import all_skills


def _names():
    return [s.name for s in all_skills()]


class MergeTest(unittest.TestCase):
    def test_merged_singles(self):
        names = _names()
        for want in ("weather", "wiki", "crypto", "translate",
                     "web_search", "fast_fetch"):
            self.assertIn(want, names, want)
            self.assertEqual(names.count(want), 1,
                             f"duplicate registration: {want}")

    def test_old_names_gone(self):
        names = set(_names())
        for gone in ("brave_search", "fast_search", "deep_web_search",
                     "deep_web_read"):
            self.assertNotIn(gone, names, gone)

    def test_deleted_modules_gone(self):
        for mod in ("skills.fast_web", "skills.deep_web",
                    "skills.routine_brave", "skills.routine_weather",
                    "skills.routine_wiki", "skills.routine_crypto",
                    "skills.routine_translate"):
            with self.assertRaises(ModuleNotFoundError, msg=mod):
                __import__(mod)

    def test_search_agent_helpers_intact(self):
        from skills.web_search import (_http_get, _strip_html,
                                       _search_ddg_html, search_all,
                                       fetch_page)
        for fn in (_http_get, _strip_html, _search_ddg_html,
                   search_all, fetch_page):
            self.assertTrue(callable(fn))

    def test_ddg_library_present(self):
        try:
            __import__("ddgs")
            present = True
        except ImportError:
            try:
                __import__("duckduckgo_search")
                present = True
            except ImportError:
                present = False
        self.assertTrue(present)

    def test_ddg_lib_search_smoke(self):
        from skills.web_search import _search_ddg_lib
        out = _search_ddg_lib("everest height meters", count=2)
        self.assertIsInstance(out, list)


if __name__ == "__main__":
    unittest.main()
