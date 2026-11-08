"""The settings UI must say what happened — every tab, not just MARKET.

1.38.0 taught the MARKET handlers to report; the follow-up extended the
same promise to skills, personality, voice, prefs, library and modules.
Two regressions motivated it, and both are pinned here:

  * a handler that discards the response body
    (``.then(function(){loadTab(...)})``) makes success and failure look
    identical — ``loadTab()`` also wipes innerHTML, so anything written
    first is erased anyway;
  * a handler whose ``catch`` does nothing lets the request vanish
    without a word.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The one delegated listener that owns every data-action handler. The
# fire-and-forget catches that remain are all best-effort housekeeping
# (health banner, savePref, stopSpeak, greeting) and live before it.
HANDLER_MARKER = "document.addEventListener('click',function(e){"

# Tabs a setNotice() call can name. paintNotice() bails out silently if
# the panel id is missing, which would lose the message entirely.
NOTICE_TABS = ("market", "skills", "personality", "voice", "audio",
               "general", "library", "modules")


class ActionFeedbackTests(unittest.TestCase):
    """Guards the notice mechanism the whole settings surface relies on."""

    @classmethod
    def setUpClass(cls):
        cls.js = (ROOT / "static" / "js" / "app.js").read_text(
            encoding="utf-8")
        cls.html = (ROOT / "templates" / "index.html").read_text(
            encoding="utf-8")

    def _handlers(self):
        self.assertIn(HANDLER_MARKER, self.js)
        return self.js.split(HANDLER_MARKER, 1)[1]

    def test_no_handler_discards_its_response_body(self):
        # Reading the body is the only way to show the server's reason.
        self.assertNotIn(".then(function(){loadTab", self.js)

    def test_no_action_handler_swallows_an_error(self):
        # Everything from the delegated listener onward must report.
        self.assertIsNone(
            re.search(r"catch\(\s*function\(\)\s*\{\s*\}\s*\)",
                      self._handlers()))

    def test_notice_carries_the_tab_it_belongs_to(self):
        # One mechanism for every panel: setNotice records where it was
        # raised, and paintNotice draws only into that panel — otherwise
        # a message for skills would land on whatever is open now.
        self.assertIn("function setNotice(text, ok, tab)", self.js)
        self.assertIn(
            "uiNotice={text:String(text||''), ok:!!ok!==false, "
            "tab:tab||activeTabName()};", self.js)
        self.assertIn("var inner=$('panel-'+tab);if(!inner)return;", self.js)
        self.assertIn("if(!tab||tab!==uiNotice.tab)return;", self.js)

    def test_a_re_render_redraws_the_notice(self):
        # loadTab() replaces innerHTML, so a notice written just before
        # it would be gone on the next frame.
        self.assertIn("if(uiNotice.tab===name)paintNotice(name);", self.js)

    def test_every_notice_target_panel_exists(self):
        # A missing id makes paintNotice() return without drawing — the
        # message would disappear with no error anywhere.
        for tab in NOTICE_TABS:
            self.assertIn('id="panel-%s"' % tab, self.html)

    def test_default_tab_is_one_the_user_can_be_on(self):
        # Handlers that do not name a tab fall back to the active one;
        # it has to be a real settings tab for data-tab to resolve.
        for tab in NOTICE_TABS:
            self.assertIn('data-tab="%s"' % tab, self.html)

    def test_the_reason_is_never_interpolated_as_html(self):
        # The reason comes from the server (and, for plugin rejects,
        # from user-supplied code) — it must be assigned as text.
        self.assertIn("label.textContent=n.text", self.js)


if __name__ == "__main__":
    unittest.main()
