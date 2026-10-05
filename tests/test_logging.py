"""Logging: rotation configured (no unbounded log growth)."""
from __future__ import annotations

import logging
import unittest


class LoggingTests(unittest.TestCase):
    def test_rotation_configured(self):
        import logger as lg
        root = logging.getLogger()
        old_handlers = list(root.handlers)
        old_flag = lg._configured
        for h in old_handlers:
            root.removeHandler(h)
        lg._configured = False
        try:
            lg.setup_logging("INFO")
            rhs = [h for h in root.handlers
                   if type(h).__name__ == "RotatingFileHandler"]
            self.assertEqual(len(rhs), 1)
            self.assertEqual(rhs[0].maxBytes, 5 * 1024 * 1024)
            self.assertEqual(rhs[0].backupCount, 3)
            self.assertTrue(str(rhs[0].baseFilename).endswith("jarvis.log"))
        finally:
            for h in list(root.handlers):
                root.removeHandler(h)
            for h in old_handlers:
                root.addHandler(h)
            lg._configured = old_flag


if __name__ == "__main__":
    unittest.main()
