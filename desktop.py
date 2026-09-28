"""JARVIS desktop launcher — run with: pythonw desktop.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from logger import setup_logging
setup_logging("INFO")

try:
    from system.launcher import run_desktop_mode
    _open = "--open" in sys.argv[1:]
    run_desktop_mode(open_browser=_open)
except Exception as exc:
    import traceback
    from logger import get_logger
    get_logger("desktop").critical("Fatal: %s\n%s", exc, traceback.format_exc())
    sys.exit(1)
