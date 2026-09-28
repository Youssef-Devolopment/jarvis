"""Desktop toast notifications — JARVIS reaches you when the tab is closed.

windows-toasts with Approve/Dismiss buttons for confirmations. Every
import lazy: without the library everything degrades to log lines and
confirm() safely defaults to False (deny).
"""
from __future__ import annotations
import threading
from logger import get_logger

log = get_logger(__name__)

_APP = "JARVIS"


def is_available() -> bool:
    try:
        __import__("windows_toasts")
        return True
    except ImportError:
        return False


def notify(title: str, message: str) -> bool:
    """Fire-and-forget toast. Returns True if shown."""
    if not is_available():
        log.info("Toast (fallback): %s — %s", title, message)
        return False
    try:
        from windows_toasts import Toast, WindowsToaster
        t = Toast()
        t.text_fields = [str(title)[:120], str(message)[:220]]
        WindowsToaster(_APP).show_toast(t)
        log.info("Toast shown: %s", title)
        return True
    except Exception as exc:
        log.debug("Toast failed: %s", exc)
        return False


def confirm(question: str, timeout: int = 120) -> bool:
    """Toast with Approve/Dismiss. Default NO on timeout/failure."""
    if not is_available():
        log.info("Confirm (no toasts, default NO): %s", question)
        return False
    done = threading.Event()
    answer = {"yes": False}
    try:
        from windows_toasts import Toast, ToastButton, WindowsToaster

        def _on_activated(args=None):
            try:
                arg = ""
                if args is not None:
                    arg = str(getattr(args, "arguments", "") or "")
                if "approve" in arg.lower():
                    answer["yes"] = True
            finally:
                done.set()

        t = Toast()
        t.text_fields = ["JARVIS needs approval", str(question)[:220]]
        t.buttons = [ToastButton("Approve", "approve"),
                     ToastButton("Dismiss", "dismiss")]
        toaster = WindowsToaster(_APP)
        toaster.on_activated = _on_activated
        toaster.show_toast(t)
        log.info("Confirm asked: %r", question[:100])
    except Exception as exc:
        log.debug("Confirm toast failed: %s", exc)
        return False
    done.wait(timeout=max(5, timeout))
    log.info("Confirm answer: %s", "YES" if answer["yes"] else "NO/timeout")
    return answer["yes"]
