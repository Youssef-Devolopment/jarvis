from __future__ import annotations
import logging, re, sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "jarvis.log"
_FMT = "%(asctime)s | %(levelname)-8s | %(name)-22s | %(filename)s:%(lineno)d | %(message)s"
_DATE = "%Y-%m-%d %H:%M:%S"
_configured = False

# --- secret redaction ------------------------------------------------------
# Patterns are deliberately broad: better a masked log line than a leaked
# key. Applied to every handler at setup; redact() is also usable standalone.
_REDACTIONS = [
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"), "sk-***"),
    (re.compile(r"\btvly-[A-Za-z0-9_\-]{6,}"), "tvly-***"),
    (re.compile(r"\bgh[pous]_[A-Za-z0-9]{16,}"), "ghp_***"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{16,}"), "github_pat_***"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}"), r"\1***"),
    (re.compile(r"(?i)\b([A-Z0-9_]*(?:API_?KEY|APIKEY|TOKEN|SECRET|"
                r"PASSWD|PASSWORD)[A-Z0-9_]*\s*[=:]\s*)[^\s\"']{6,}"),
     r"\1***"),
    (re.compile(r"(?i)([?&](?:key|token|api_?key|apikey)=)[^&\s\"']+"),
     r"\1***"),
]


def redact(text: str) -> str:
    """Mask anything that looks like a credential in free text."""
    if not text:
        return text
    for pattern, repl in _REDACTIONS:
        text = pattern.sub(repl, text)
    return text


class RedactFilter(logging.Filter):
    """Rewrites each record's message so secrets never reach a handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        clean = redact(msg)
        if clean != msg:
            record.msg = clean
            record.args = ()
        return True


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
    ch.addFilter(RedactFilter())
    root.addHandler(ch)
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024,
                             backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT, _DATE))
    fh.addFilter(RedactFilter())
    root.addHandler(fh)


def setup_logging(level: str = "INFO") -> None:
    _configure(level)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
