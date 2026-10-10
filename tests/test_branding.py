"""Brand assets: the six shipped SVGs exist, parse, and stay
self-contained, so the README banner, landing page and favicons can
never silently break."""
from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = [
    "assets/jarvis-logo.svg",        # self-contained README banner
    "assets/jarvis-logo-mark.svg",   # icon-only mark (transparent)
    "assets/jarvis-favicon.svg",     # favicon (app/repo)
    "docs/favicon.svg",              # favicon (landing page)
    "docs/logo-dark.svg",            # lockup for dark backgrounds
    "docs/logo-light.svg",           # lockup for light backgrounds
]
LOCKUPS = ("assets/jarvis-logo.svg", "docs/logo-dark.svg", "docs/logo-light.svg")
SVG_NS = "http://www.w3.org/2000/svg"


class BrandAssetTests(unittest.TestCase):
    def test_all_six_files_exist(self):
        missing = [f for f in FILES if not (ROOT / f).is_file()]
        self.assertEqual(missing, [], "missing brand assets: %s" % missing)

    def test_each_parses_as_svg_with_a_viewbox(self):
        for f in FILES:
            root = ET.parse(ROOT / f).getroot()
            # ElementTree folds the xmlns declaration into the tag
            self.assertEqual(root.tag, "{%s}svg" % SVG_NS, f)
            self.assertIn("viewBox", root.attrib, f)

    def test_assets_are_self_contained(self):
        """No external images or remote fetches: logos must render in
        READMEs, camo proxies and offline docs identically."""
        for f in FILES:
            data = (ROOT / f).read_text(encoding="utf-8")
            self.assertNotIn("<image", data, f)
            self.assertNotIn("https://", data, f)
            self.assertNotIn(
                "http://",
                data.replace('xmlns="%s"' % SVG_NS, ""),
                f,
            )

    def test_lockups_carry_the_wordmark_and_the_mark_geometry(self):
        for f in LOCKUPS:
            data = (ROOT / f).read_text(encoding="utf-8")
            self.assertIn("JARVIS", data, f)   # wordmark
            self.assertIn("M32 3", data, f)    # diamond mark path


if __name__ == "__main__":
    unittest.main()
