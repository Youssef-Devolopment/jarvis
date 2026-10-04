"""Scheduled-task XML: working directory set, delay kept, and the
legacy fallback preserved."""
from __future__ import annotations

import unittest
from unittest import mock

from system import autostart as au


class TaskXmlTests(unittest.TestCase):
    def test_xml_has_workdir_delay_principal(self):
        xml = au._task_xml()
        self.assertIn("<WorkingDirectory>", xml)
        self.assertIn(str(au._PROJECT), xml)
        self.assertIn("<Delay>PT15S</Delay>", xml)
        self.assertIn("<LogonType>InteractiveToken</LogonType>", xml)
        self.assertIn("desktop.py --open", xml)
        self.assertIn(str(au._pythonw()), xml)

    def test_xml_is_wellformed(self):
        import xml.dom.minidom
        xml.dom.minidom.parseString(au._task_xml())

    def test_create_uses_xml_file(self):
        seen = {}

        class R:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kw):
            seen["cmd"] = cmd
            if "/xml" in cmd:
                idx = cmd.index("/xml")
                seen["xml"] = open(cmd[idx + 1], encoding="utf-16").read()
            return R()

        with mock.patch.object(au.subprocess, "run",
                               side_effect=fake_run):
            self.assertTrue(au._task_create())
        self.assertIn("/xml", seen["cmd"])
        self.assertIn("<WorkingDirectory>", seen["xml"])

    def test_create_falls_back_to_legacy(self):
        calls = []

        class Bad:
            returncode = 1
            stdout = ""
            stderr = "denied"

        class Good:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, **kw):
            calls.append(cmd)
            return Bad() if "/xml" in cmd else Good()

        with mock.patch.object(au.subprocess, "run",
                               side_effect=fake_run):
            self.assertTrue(au._task_create())
        self.assertEqual(len(calls), 2)
        self.assertIn("/tr", calls[1])

    def test_create_false_when_all_fail(self):
        class Bad:
            returncode = 1
            stdout = ""
            stderr = "denied"

        with mock.patch.object(au.subprocess, "run",
                               return_value=Bad()):
            self.assertFalse(au._task_create())


if __name__ == "__main__":
    unittest.main()
