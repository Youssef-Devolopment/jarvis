"""Interpreter hand skill — voice gateway to Open Interpreter.

"Computer, organize my downloads" -> runs in background, JARVIS speaks
the result when done. Fire-and-forget: the HTTP request never waits on
the model. Unavailable package -> install hint, never a crash.
"""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _done_summary(res: dict) -> str:
    if res.get("ok"):
        out = (res.get("output") or "").strip()
        if len(out) > 400:
            out = out[:400] + "..."
        return f"Done, sir. {out}" if out else "Done, sir."
    return f"It failed, sir: {(res.get('error') or 'unknown error')[:200]}"


def _launch(task: str) -> str:
    try:
        from system.interpreter_hand import (
            is_available, run_goal_async, status)
    except Exception as exc:
        log.warning("Interpreter hand import failed: %s", exc)
        return "The computer hand is not wired up."
    if not is_available():
        return status().get("error", "Hand not installed.")
    log.info("Interpreter task: %r", task[:100])

    def _finished(res: dict):
        msg = _done_summary(res)
        log.info("Interpreter finished: %r", msg[:120])
        try:
            from voice import speak_async
            speak_async(msg)
        except Exception as exc:
            log.warning("Result speech failed: %s", exc)
        try:
            from system import overlay
            overlay.notice(msg[:70])
        except Exception:
            pass

    run_goal_async(task, on_done=_finished)
    return "Working on it, sir — I'll tell you when it's done."


@register("computer_task", [
    r"^(?:computer|hey\s+computer)[,:\s]+(?P<task>.+?)[\?\.\!]?$",
    r"^(?:ask\s+(?:the\s+)?computer\s+to)\s+(?P<task2>.+?)[\?\.\!]?$",
], "Run a computer task via Open Interpreter")
def s_computer(text, m):
    gd = m.groupdict()
    task = (gd.get("task") or gd.get("task2") or "").strip()
    if not task or len(task) < 3:
        return None
    return _launch(task)
