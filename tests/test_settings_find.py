"""Settings findability contracts - the 21-tab rail people navigate by.

1.35.x left settings as a flat row of 21 tabs; "features are hard to
find" was the complaint behind it. The fix is a grouped rail plus one
search box that matches what a tab *controls* ("microphone") rather
than what it is named ("AUDIO").

None of that survives a well-meaning edit: a new tab without a group
reappears as an orphan, a tab without keywords silently drops out of
search, and a tab whose CSS overrides `[hidden]` stays on screen after
being filtered. These tests hold the wiring still.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _settings_block():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    start = html.index('<div class="settings-rail"')
    # Other modals also have a .modal-body - the rail's one is the first
    # *after* the rail starts. Panels live past that boundary, so the
    # block ends where the settings modal's own body ends.
    end = html.index('id="modal-body"')
    return html[start:end]


def _html():
    return (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def _attrs(block, pattern):
    """Every match of `pattern`, as dicts of attributes."""
    return [dict(re.findall(r'([\w-]+)="([^"]*)"', m)) for m in
            re.findall(pattern, block)]


TABS = _attrs(_settings_block(), r'<button class="tab[^>]*>')
PANELS = _attrs(_html(), r'<div class="tab-panel[^>]*>')


class TabRailTests(unittest.TestCase):
    """One tab per panel, all of them inside a named group."""

    def test_every_tab_has_exactly_one_panel(self):
        tabs = [t.get("data-tab") for t in TABS]
        panels = [p.get("data-panel") for p in PANELS]
        self.assertEqual(sorted(tabs), sorted(panels),
                         "a tab was added or removed without its panel")

    def test_only_one_tab_and_one_panel_start_active(self):
        self.assertEqual([t for t in TABS if t.get("class") == "tab active"],
                         [t for t in TABS if t.get("data-tab") == "model"])
        self.assertEqual(
            [p for p in PANELS if "active" in p.get("class", "").split()],
            [p for p in PANELS if p.get("data-panel") == "model"])

    def test_every_tab_declares_a_group(self):
        names = {g.get("data-group") for g in
                 _attrs(_settings_block(), r'<div class="tab-group"[^>]*>')}
        for tab in TABS:
            self.assertIn(tab.get("data-group"), names,
                          f"{tab.get('data-tab')} is not inside any group")

    def test_every_group_holds_at_least_one_tab(self):
        declared = [g.get("data-group") for g in
                    _attrs(_settings_block(),
                           r'<div class="tab-group"[^>]*>')]
        for group in dict.fromkeys(declared):
            self.assertTrue(
                any(t.get("data-group") == group for t in TABS),
                f"the {group.upper()} header has no tabs under it")


class TabKeywordTests(unittest.TestCase):
    """Search matches the tab's keywords, so keywords are the contract."""

    def test_every_tab_has_keywords(self):
        for tab in TABS:
            self.assertTrue(
                (tab.get("data-keywords") or "").strip(),
                f"{tab.get('data-tab')} has no data-keywords and would "
                f"only be findable by its own name")

    def test_search_words_people_actually_use(self):
        # Chosen from the words in the support question this fixes.
        by_tab = {t.get("data-tab"): (t.get("data-keywords") or "")
                  for t in TABS}
        self.assertIn("microphone", by_tab["audio"])
        self.assertIn("api key", by_tab["model"])
        self.assertIn("theme", by_tab["appearance"])
        self.assertIn("install", by_tab["library"])
        self.assertIn("health", by_tab["system"])

    def test_tab_labels_are_in_their_own_keyword_haystack(self):
        html = (ROOT / "templates" / "index.html").read_text(
            encoding="utf-8")
        for tab in TABS:
            name = tab.get("data-tab")
            open_tag = html.index(f'data-tab="{name}"')
            label = re.search(r'>([A-Z]{2,})</button>',
                              html[open_tag:open_tag + 400]).group(1).lower()
            self.assertIn(
                label, (tab.get("data-keywords") or "").lower(),
                f"{name.upper()} is not findable by its own label")


class SearchSurfaceTests(unittest.TestCase):
    """The box, its affordances, and the CSS that makes them work."""

    def setUp(self):
        self.html = _settings_block()
        self.css = (ROOT / "static" / "css" / "style.css").read_text(
            encoding="utf-8")
        self.js = (ROOT / "static" / "js" / "app.js").read_text(
            encoding="utf-8")

    def test_box_and_its_affordances_exist(self):
        self.assertIn('id="settings-search"', self.html)
        self.assertIn('aria-label="Search settings"', self.html)
        self.assertIn('id="settings-search-clear"', self.html)
        self.assertIn('aria-label="Clear search"', self.html)
        self.assertIn('id="settings-search-count"', self.html)
        self.assertIn('aria-live="polite"', self.html)
        self.assertIn('id="settings-empty"', self.html)

    def test_the_search_functions_are_wired_into_the_app(self):
        for needle in ("function filterSettings(", "function settingsTabs(",
                       "function clearSettingsSearch(",
                       "function wireSettingsSearch(", "wireSettingsSearch();"):
            self.assertIn(needle, self.js)

    def test_enter_opens_the_first_match_and_slash_focuses_search(self):
        self.assertIn("e.key==='Enter'", self.js)
        # the handler ignores Ctrl/Cmd+... so typing a slash in a field
        # still works
        self.assertIn("e.key!=='/'", self.js)
        self.assertIn("e.key==='Escape'", self.js)

    def test_selection_state_is_reported_to_screen_readers(self):
        # aria-selected has to be refreshed on every tab change, not just
        # written once in the template.
        self.assertIn("setAttribute('aria-selected'", self.js)

    def test_filtered_out_tabs_actually_disappear(self):
        # An author `display:` rule beats the UA's [hidden]{display:none},
        # so the filter would run, count correctly, and change nothing
        # visible without this rule. The starter chips and key banner
        # carry the same one.
        self.assertIn(".tab[hidden]", self.css)
        self.assertIn(".tab-group[hidden]", self.css)
        self.assertIn(".settings-empty[hidden]", self.css)

    def test_the_rail_is_a_rail_at_every_width(self):
        # Desktop: a vertical column. Narrow: a horizontal strip again.
        self.assertIn("flex-direction:column", self.css)
        self.assertIn(".settings-body{flex-direction:column", self.css)


if __name__ == "__main__":
    unittest.main()
