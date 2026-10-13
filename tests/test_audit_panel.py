"""v1.27.0 — audit panel surface guards.

The AUDIT tab renders the /api/audit trail newest-first with status
chips. Guards: template landmarks exist, the loader fetches the
endpoint, the renderer parses lines into chips (never raw HTML —
everything through esc()), and REFRESH reloads. No new CSS: the
panel reuses set-list/set-row/schip/dbtn.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _js():
    return (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")


def _audit_block():
    js = _js()
    start = js.index("if(name==='audit')")
    tail = js[start:]
    end = tail.index("\n  if(name===", 1)
    return tail[:end]


class AuditTemplateTests(unittest.TestCase):
    def setUp(self):
        self.html = (ROOT / "templates" / "index.html").read_text(
            encoding="utf-8")

    def test_audit_tab_button_and_panel_exist(self):
        self.assertIn('data-tab="audit"', self.html)
        self.assertIn('data-panel="audit"', self.html)
        self.assertIn('id="panel-audit"', self.html)

    def test_audit_tab_sits_with_system_tabs(self):
        tabrow = self.html[self.html.index("modal-tabs"):
                           self.html.index("modal-tabs") + 3000]
        self.assertIn('data-tab="system"', tabrow)
        self.assertIn('data-tab="audit"', tabrow)


class AuditLoaderTests(unittest.TestCase):
    def test_endpoint_mapped(self):
        self.assertIn("audit:'/api/audit?limit=50'", _js())

    def test_refresh_action_reloads_tab(self):
        js = _js()
        self.assertIn("'audit-refresh'", js)
        start = js.index("'audit-refresh'")
        self.assertIn("loadTab('audit')", js[start:start + 200])


class AuditRendererTests(unittest.TestCase):
    def test_renders_chips_rows_and_refresh(self):
        block = _audit_block()
        self.assertIn("AUDIT TRAIL (", block)
        # class built dynamically from status: 'schip--'+st where
        # st maps OK->ok, FAIL->degraded, else unknown
        self.assertIn("schip--'+st", block)
        self.assertIn("'ok':'degraded'", block)
        self.assertIn("'unknown'", block)
        self.assertIn('data-action="audit-refresh"', block)

    def test_everything_escaped(self):
        # audit lines carry file paths and args — raw innerHTML
        # would be an XSS hole. The renderer must esc every piece.
        block = _audit_block()
        self.assertGreaterEqual(block.count("esc("), 3)
        self.assertNotIn("innerHTML", block)

    def test_unparsed_lines_degrade_to_raw_row(self):
        block = _audit_block()
        self.assertIn("'unknown'", block)
        self.assertIn("'raw'", block)
        self.assertIn("No entries yet", block)

    def test_reuses_existing_components_only(self):
        block = _audit_block()
        for cls in ("set-list", "set-row", "label", "actions", "dbtn"):
            self.assertIn(cls, block)


if __name__ == "__main__":
    unittest.main()
