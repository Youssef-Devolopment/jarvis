"""Logging: rotation configured + secrets redacted (never written in the clear)."""
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

    def test_handlers_carry_redact_filter(self):
        import logger as lg
        root = logging.getLogger()
        old_handlers = list(root.handlers)
        old_flag = lg._configured
        for h in old_handlers:
            root.removeHandler(h)
        lg._configured = False
        try:
            lg.setup_logging("INFO")
            self.assertTrue(root.handlers)
            for h in root.handlers:
                self.assertTrue(
                    any(isinstance(f, lg.RedactFilter) for f in h.filters),
                    f"handler {h} missing RedactFilter")
        finally:
            for h in list(root.handlers):
                root.removeHandler(h)
            for h in old_handlers:
                root.addHandler(h)
            lg._configured = old_flag


class RedactionTests(unittest.TestCase):
    def test_openai_style_key_masked(self):
        import logger as lg
        out = lg.redact("calling with sk-abc123def456ghi789 now")
        self.assertNotIn("sk-abc123def456ghi789", out)
        self.assertIn("sk-***", out)

    def test_tavily_key_masked(self):
        import logger as lg
        self.assertNotIn("tvly-1234567ab", lg.redact("tavily tvly-1234567ab ok"))

    def test_github_token_masked(self):
        import logger as lg
        out = lg.redact("pushing with ghp_abcdefghijklmnopqrstuv")
        self.assertNotIn("ghp_abcdefghijklmnopqrstuv", out)
        self.assertIn("ghp_***", out)

    def test_bearer_header_masked(self):
        import logger as lg
        out = lg.redact("Authorization: Bearer abcdefghijklmnop1234")
        self.assertNotIn("abcdefghijklmnop1234", out)
        self.assertIn("Bearer ***", out)

    def test_env_assignment_masked(self):
        import logger as lg
        out = lg.redact("GROQ_API_KEY=abcdef123456 loaded fine")
        self.assertNotIn("abcdef123456", out)
        self.assertIn("***", out)

    def test_query_param_masked(self):
        import logger as lg
        out = lg.redact("https://x.test/s?key=supersecret123&y=1")
        self.assertNotIn("supersecret123", out)

    def test_plain_text_untouched(self):
        import logger as lg
        self.assertEqual(lg.redact("hello world"), "hello world")
        self.assertEqual(lg.redact(""), "")

    def test_filter_rewrites_record_message(self):
        import logger as lg
        rec = logging.LogRecord("t", logging.INFO, __file__, 1,
                                "token is sk-abcdefghijk1234567", None, None)
        self.assertTrue(lg.RedactFilter().filter(rec))
        self.assertNotIn("sk-abcdefghijk1234567", rec.getMessage())

    def test_filter_leaves_clean_records_alone(self):
        import logger as lg
        rec = logging.LogRecord("t", logging.INFO, __file__, 1,
                                "all fine %s", ("mate",), None)
        self.assertTrue(lg.RedactFilter().filter(rec))
        self.assertEqual(rec.getMessage(), "all fine mate")


if __name__ == "__main__":
    unittest.main()
