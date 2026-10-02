"""Omniscience — lightweight background screen-context capture loop.

Security model (important):
  * frames live in RAM only — nothing is ever written to disk;
  * the loop itself makes ZERO API calls (vision runs on demand);
  * kill switch: pref ``screen_loop_enabled`` (default on) — flipping
    it off stops the loop on its next tick;
  * interval: pref ``screen_loop_interval`` seconds (default 20,
    clamped to 5..300).

The loop keeps one downscaled frame + timestamp, so "what's on my
screen / fix this error" answers are instant: the freshest frame is
usually <20s old, otherwise a live grab is taken.
"""
from __future__ import annotations

import io
import threading
import time
from logger import get_logger

log = get_logger(__name__)

_MAX_W = 1280
_lock = threading.Lock()
_state = {"frame": None, "at": 0.0, "size": "", "running": False,
          "captures": 0, "errors": 0}
_stop = threading.Event()
_thread: threading.Thread | None = None


# ----- prefs --------------------------------------------------------------
def _enabled() -> bool:
    try:
        from memory import get_pref
        return bool(get_pref("screen_loop_enabled", True))
    except Exception:
        return True


def _interval() -> float:
    try:
        from memory import get_pref
        v = float(get_pref("screen_loop_interval", 20))
    except Exception:
        v = 20.0
    return max(5.0, min(300.0, v))


# ----- capture ------------------------------------------------------------
def _grab():
    """Grab + downscale one frame. Returns a PIL image or None."""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        if img.width > _MAX_W:
            ratio = _MAX_W / float(img.width)
            img = img.resize((_MAX_W, int(img.height * ratio)))
        return img
    except Exception as exc:
        with _lock:
            _state["errors"] += 1
        log.debug("screen grab failed: %s", exc)
        return None


def capture_now():
    """Synchronous capture — used when the cached frame is stale."""
    img = _grab()
    if img is not None:
        with _lock:
            _state["frame"] = img
            _state["at"] = time.time()
            _state["size"] = f"{img.width}x{img.height}"
            _state["captures"] += 1
    return img


def latest(max_age: float | None = None):
    """Return (frame, age_seconds) or (None, age) when stale/absent."""
    with _lock:
        frame = _state["frame"]
        at = _state["at"]
    age = (time.time() - at) if at else 1e9
    if frame is None:
        return None, age
    if max_age is not None and age > max_age:
        return None, age
    return frame, age


# ----- on-demand vision ---------------------------------------------------
def ask(question: str | None = None) -> str:
    """Answer a question about the current screen content.

    Uses the freshest cached frame (age <= interval + 10s); otherwise
    grabs a live frame first. One vision call, no disk I/O.
    """
    question = (question or "").strip() or (
        "Extract all visible text from this screenshot. Preserve line "
        "breaks. Return only the text.")
    frame, _age = latest(max_age=_interval() + 10)
    if frame is None:
        frame = capture_now()
    if frame is None:
        return "[error] could not capture screen"
    from ai import screen_text
    return screen_text.ask_image(frame, question)


# ----- loop ---------------------------------------------------------------
def _run() -> None:
    log.info("Screen-context loop started (interval %.0fs, RAM-only)",
             _interval())
    try:
        while not _stop.is_set():
            if not _enabled():
                _stop.wait(3.0)
                continue
            capture_now()
            _stop.wait(_interval())
    finally:
        with _lock:
            _state["running"] = False
        log.info("Screen-context loop stopped")


def start() -> bool:
    """Start the loop once (no-op when already running)."""
    global _thread
    if not _enabled():
        log.info("Screen-context loop disabled by pref")
        return False
    with _lock:
        if _thread and _thread.is_alive():
            return True
        _stop.clear()
        _state["running"] = True
        _thread = threading.Thread(target=_run, daemon=True,
                                   name="jarvis-screen-context")
        _thread.start()
    return True


def stop() -> bool:
    _stop.set()
    with _lock:
        _state["running"] = False
    return True


def status() -> dict:
    with _lock:
        frame = _state["frame"]
        d = {k: _state[k] for k in
             ("at", "size", "running", "captures", "errors")}
    d["enabled"] = _enabled()
    d["interval"] = _interval()
    d["age"] = round(time.time() - d["at"], 1) if d["at"] else None
    d["in_ram"] = frame is not None
    d["disk_writes"] = 0          # by design — RAM-only frames
    return d
