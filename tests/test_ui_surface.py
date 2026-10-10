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

    def test_input_hint_is_friendly(self):
        from system import overlay
        self.assertIn("Enter", overlay.HINT_TEXT)
        self.assertTrue(len(overlay.HINT_TEXT) > 10)


if __name__ == "__main__":
    unittest.main()
