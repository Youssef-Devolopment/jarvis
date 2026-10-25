"""CI-gate contracts: the two workflows that stand in for a human clicking.

CI says "the tree is sound"; the Installer workflow says "the file a
user downloads actually installs". They are also the two places where a
change can quietly stop being checked at all.

1.36.0 shipped `installer.yml` as the only file in the repo that did not
pin an interpreter - it took whatever `python` the runner image happened
to carry, while `ci.yml` pinned 3.10. The v1.36.0 tag then failed its
bootstrap step twice at ~23 s, identically, and the job log needed a
GitHub sign-in to read, so the failure was simultaneously unexplained
and unfixable from the outside.

Pinning the interpreter and printing the install log are what closed
it. These tests hold both in place: nothing here needs a runner, a
network or PyYAML, only the workflow files themselves.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"


def _read(name):
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _pinned_python(text):
    """The interpreter a workflow pins via actions/setup-python, if any.

    `ci.yml` holds its version in a matrix (`["3.10"]`) and refers to it
    as `${{ matrix.python-version }}`; `installer.yml` writes it inline.
    Both are accepted; a bare template reference still resolves to None.
    """
    m = re.search(r"python-version:\s*\[?\s*[\"']?([\d.]+)[\"']?", text)
    return m.group(1) if m else None


class InterpreterPinningTests(unittest.TestCase):
    """The bootstrap must not inherit an interpreter from the image."""

    def test_installer_job_pins_an_interpreter(self):
        text = _read("installer.yml")
        self.assertIn("actions/setup-python", text,
                      "the installer job takes whatever Python the runner "
                      "image ships - pin it like ci.yml does")
        self.assertIsNotNone(_pinned_python(text),
                             "setup-python without python-version")

    def test_installer_pins_the_same_python_as_ci(self):
        # The gate has to bootstrap the interpreter the suite is tested
        # with. Two pins that drift apart is the same bug, deferred.
        ci = _pinned_python(_read("ci.yml"))
        installer = _pinned_python(_read("installer.yml"))
        self.assertIsNotNone(ci, "ci.yml no longer pins an interpreter")
        self.assertEqual(installer, ci,
                         "the installer gate tests a different Python than "
                         "the test suite does")

    def test_python_is_pinned_before_the_installer_is_built(self):
        text = _read("installer.yml")
        if "actions/setup-python" not in text:
            self.skipTest("no setup-python step to order")
        self.assertLess(text.index("actions/setup-python"),
                        text.index("installer/build.ps1"),
                        "Python is set up after the build step, so the "
                        "build cannot depend on it")


class BootstrapFailureTests(unittest.TestCase):
    """A dead bootstrap must say why, inside the step that failed."""

    def test_a_failed_bootstrap_prints_the_install_log(self):
        # install-deps.ps1 already tees every step and all of pip's
        # output into logs\install.log; a workflow that throws without
        # printing it throws away the only diagnosis.
        text = _read("installer.yml")
        self.assertIn("install.log", text,
                      "the bootstrap step no longer surfaces the log")
        self.assertIn("-Tail", text,
                      "the log is not read as a tail, so the reason is "
                      "buried under the whole install")
        self.assertIn("install-deps.ps1 exited", text,
                      "the bootstrap no longer reports a non-zero exit")


if __name__ == "__main__":
    unittest.main()
