"""Test package: keep the suite hermetic.

Setting JARVIS_LOG_DIR here — before any test module imports `logger` —
points every file handler at a scratch directory instead of the real
logs/jarvis.log. Discovery imports this package first, so the override is
in place before `setup_logging()` can attach anything.
"""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "JARVIS_LOG_DIR",
    tempfile.mkdtemp(prefix="jarvis-test-log-"),
)
