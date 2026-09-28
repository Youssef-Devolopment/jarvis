from __future__ import annotations
import logging, sys
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "jarvis.log"
_FMT = "%(asctime)s | %(levelname)-8s | %(name)-22s | %(filename)s:%(lineno)d | %(message)s"
_DATE = "%Y-%m-%d %H:%M:%S"
_configured = False


def _configure(level: str = "INFO") -> None:
    global _configured
    if _configured:
        return
    _configured = True
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter(_FMT, _DATE))
    root.addHandler(ch)
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT, _DATE))
    root.addHandler(fh)


def setup_logging(level: str = "INFO") -> None:
    _configure(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
