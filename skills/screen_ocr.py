"""Screen reading — capture the monitor and OCR it (mss + easyocr).

Lets JARVIS "read" errors or status text off your screen without
slow disk-heavy screenshots: mss grabs straight to memory.
easyocr runs on CPU with English + Arabic. Both imports are lazy —
the skill degrades to an install hint when a library is missing.
"""
from __future__ import annotations
import threading
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_lock = threading.Lock()
_reader = None
_MAX_CHARS = 1500


def _has(mod: str) -> bool:
    try:
        __import__(mod)
        return True
    except ImportError:
        return False


def _get_reader():
    global _reader
    with _lock:
        if _reader is None:
            import easyocr
            log.info("Loading OCR reader (first use downloads models)...")
            _reader = easyocr.Reader(["en", "ar"], gpu=False)
            log.info("OCR reader ready")
        return _reader


def read_screen() -> str:
    """Capture the primary monitor and return visible text."""
    if not _has("mss"):
        return "Screen capture needs the mss package. Run: pip install mss"
    if not _has("easyocr"):
        return ("Text reading needs easyocr (plus torch, a large download). "
                "Run: pip install easyocr")
    try:
        import mss
        import numpy as np
        from PIL import Image
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])  # primary monitor
            img = Image.frombytes("RGB", shot.size, shot.rgb)
        frame = np.asarray(img)
    except Exception as exc:
        log.warning("Screen capture failed: %s", exc)
        return "Could not capture the screen."
    try:
        reader = _get_reader()
        lines = reader.readtext(frame, detail=0, paragraph=True)
    except Exception as exc:
        log.warning("OCR failed: %s", exc)
        return ("OCR engine failed to start. It may still be downloading "
                "models — try again in a minute.")
    text = "\n".join(str(x).strip() for x in lines if str(x).strip())
    if not text:
        return "I can see the screen, but there's no readable text on it."
    if len(text) > _MAX_CHARS:
        text = text[:_MAX_CHARS] + "\n...(truncated)"
    try:
        from memory import context as ctx
        ctx.log_event("vision", f"screen read: {text[:150]}")
    except Exception:
        pass
    return text


@register("read_screen", [
    r"^(?:read\s+(?:my\s+)?screen|what(?:'s| is)(?:\s+on)?\s+my\s+screen)[\?\.\!]?$",
    r"^(?:read\s+the\s+error(?:\s+on\s+(?:my\s+)?screen)?|what\s+does\s+(?:the\s+)?(?:error|screen)\s+say)[\?\.\!]?$",
], "Read text visible on the screen")
def s_read_screen(text, m):
    return read_screen()
