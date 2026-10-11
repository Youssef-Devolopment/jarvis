"""UI surface guards — template/CSS contracts the polish pass relies on.

1.17.0 fixed a real product bug (the key/health banners rendered
buried behind the fixed topbar) — the wrapper + pinned position are
now guarded so they cannot silently regress. Also locks the overlay
HUD's brand palette and friendly input hint.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class TemplateSurfaceTests(unittest.TestCase):
    """The index.html landmarks every product flow wires to."""

    def setUp(self):
        self.html = (ROOT / "templates" / "index.html").read_text(
            encoding="utf-8")

    def test_status_pill_and_banners_present(self):
        for marker in ('id="status-pill"', 'id="key-banner"',
                       'id="health-banner"', 'id="starter-chips"'):
            self.assertIn(marker, self.html)

    def test_banner_wrapper_pinned_below_topbar(self):
        # both banners live inside a fixed wrapper — without it they
        # stacked at document top and hid behind the topbar (1.17.0)
        self.assertIn('class="banners"', self.html)
        start = self.html.index('class="banners"')
        block = self.html[start:start + 1400]
        self.assertIn('id="key-banner"', block)
        self.assertIn('id="health-banner"', block)

    def test_cache_buster_on_assets(self):
        self.assertIn("?v={{ version }}", self.html)

    def test_version_fallback_uses_template(self):
        # a hardcoded "v1.x.y" fallback went stale the moment the
        # version moved — the template must supply it
        self.assertIn('id="brand-ver">v{{ version }}<', self.html)


class CssSurfaceTests(unittest.TestCase):
    """Component styles the new first-run + SYSTEM surfaces need."""

    def setUp(self):
        self.css = (ROOT / "static" / "css" / "style.css").read_text(
            encoding="utf-8")

    def test_first_run_and_system_components_exist(self):
        for marker in (".onboard-card", ".onboard-head", ".onboard-sub",
                       ".sys-verdict", ".sys-warnbox", ".sys-row",
                       ".banners{"):
            self.assertIn(marker, self.css)

    def test_system_row_status_colors(self):
        for marker in (".sys-row.sys-ok", ".sys-row.sys-warn",
                       ".sys-row.sys-degraded"):
            self.assertIn(marker, self.css)

    def test_status_chip_component_has_all_variants(self):
        # 1.18.0 — SYSTEM rows render tinted pills, not loose colored
        # text; every status the API can return needs a style
        self.assertIn(".schip{", self.css)
        for variant in ("schip--ok", "schip--info", "schip--warn",
                        "schip--degraded", "schip--unknown"):
            self.assertIn("." + variant, self.css)

    def test_log_warnings_get_a_rail_not_just_color(self):
        # a failed step must be findable at a glance
        self.assertIn(".log-entry.warn{", self.css)
        self.assertIn(".log-entry.error{", self.css)
        self.assertIn("border-left:2px solid rgba(255,184,77,.55)",
                      self.css)

    def test_idle_tagline_follows_health(self):
        # the center of the screen must not say SYSTEM ONLINE while
        # the pill says SAFE MODE
        self.assertIn('body[data-state="idle"][data-health="warn"] .tagline',
                      self.css)
        self.assertIn(
            'body[data-state="idle"][data-health="degraded"] .tagline',
            self.css)


class AppJsSurfaceTests(unittest.TestCase):
    """JS behaviours the first-run flow depends on."""

    def setUp(self):
        self.js = (ROOT / "static" / "js" / "app.js").read_text(
            encoding="utf-8")

    def test_starters_respect_hidden_onboarding(self):
        # on narrow windows the onboarding card sits inside the hidden
        # .logpanel — the chips must NOT be suppressed by a card the
        # user cannot see (1.17.1)
        self.assertIn("offsetParent", self.js)

    def test_status_rows_emit_chip_markup(self):
        # SYSTEM rows use the .schip pill component for every status
        self.assertIn("schip schip--", self.js)

    def test_first_run_card_advertises_skills_without_a_key(self):
        self.assertIn("SKILLS ACTIVE", self.js)

    def test_tagline_owned_by_the_state_machine(self):
        # setState() must be the ONLY writer of the tagline, or the
        # health verdict gets clobbered back to SYSTEM ONLINE by
        # call sites that reset the UI after speaking/mic/etc.
        import re
        writers = re.findall(r"setText\('tagline'", self.js)
        owners = re.findall(r"function setState\(", self.js)
        self.assertEqual(len(owners), 1)
        # all remaining writes live inside setState + updateStatusPill
        self.assertLessEqual(len(writers), 3)
        self.assertNotIn(
            "setState(STATE.IDLE);setText('tagline'", self.js)

    def test_health_banner_messages_are_plain_english(self):
        self.assertIn("Some features are off", self.js)
        self.assertIn("details in SYSTEM", self.js)


class OverlayPaletteTests(unittest.TestCase):
    """The HUD wears the same brand colors as the app and the site."""

    def test_brand_accent(self):
        from system import overlay
        self.assertEqual(overlay.EDGE, "#66FFA3")   # brand green
        self.assertEqual(overlay.GOOD, overlay.EDGE)

    def test_state_colors_stable(self):
        from system import overlay
        self.assertEqual(overlay.BUSY, "#FFB020")
        self.assertEqual(overlay.DANGER, "#FF5C7A")

    def test_listening_state_uses_brand_cyan(self):
        # 1.18.0: listening is cyan everywhere — app pill, tagline
        # and the HUD status dot must agree
        from system import overlay
        self.assertEqual(overlay.CYAN, "#66E0FF")

    def test_key_hints_use_readable_separators(self):
        src = (ROOT / "system" / "overlay.py").read_text(encoding="utf-8")
        self.assertIn("SEND \\u00b7 ESC CLOSE", src)

    def test_copy_control_is_pill_shown_only_with_a_reply(self):
        src = (ROOT / "system" / "overlay.py").read_text(encoding="utf-8")
        self.assertIn("def _copy_show", src)
        self.assertIn("copy_bg", src)

    def test_input_hint_is_friendly(self):
        from system import overlay
        self.assertIn("Enter", overlay.HINT_TEXT)
        self.assertTrue(len(overlay.HINT_TEXT) > 10)

    def test_chrome_surface_stays_behind_content(self):
        # 1.19.3: draw_chrome recreates the deck surface on every mode
        # switch, and a recreated item lands on top of the stacking order
        # - which buried the brand title, status dot, close button, quick
        # chips, key hints and COPY pill (canvas windows float on Windows
        # because they are real child HWNDs, so only pure canvas items
        # were affected). The surface must be pushed back under content.
        src = (ROOT / "system" / "overlay.py").read_text(encoding="utf-8")
        self.assertIn('cv.tag_lower("chrome")', src)


if __name__ == "__main__":
    unittest.main()
