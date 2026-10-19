"""The tray's dashboard link must follow PORT.

`system/tray.py` hardcoded `http://127.0.0.1:5000` while the launcher,
the overlay and `config.py` all honour `PORT`. Console mode runs through
that code path, so anyone who moved the port got a dead "Open JARVIS"
link — the kind of thing that only shows up after install.
"""
from __future__ import annotations

import os
import unittest


class TrayUrlTests(unittest.TestCase):
    def test_link_follows_the_configured_port(self):
        from system import tray
        backup = os.environ.get("PORT")
        os.environ["PORT"] = "5099"
        try:
            self.assertEqual(tray._dashboard_url(),
                             "http://127.0.0.1:5099")
        finally:
            if backup is None:
                os.environ.pop("PORT", None)
            else:
                os.environ["PORT"] = backup

    def test_default_port_is_5000(self):
        from system import tray
        backup = os.environ.pop("PORT", None)
        try:
            self.assertEqual(tray._dashboard_url(),
                             "http://127.0.0.1:5000")
        finally:
            if backup is not None:
                os.environ["PORT"] = backup

    def test_no_hardcoded_url_survives_in_the_module(self):
        # A regression guard for the literal that caused this: any
        # module-level URL constant would go stale the same way.
        from system import tray
        self.assertFalse(hasattr(tray, "_URL"))


if __name__ == "__main__":
    unittest.main()
