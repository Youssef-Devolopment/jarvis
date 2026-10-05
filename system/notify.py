"""Desktop toast notifications — JARVIS reaches you when the tab is closed.

windows-toasts with Approve/Dismiss buttons for confirmations. Every
import lazy: without the library everything degrades to log lines and
confirm() safely defaults to False (deny).
"""
from __future__ import annotations
import platform
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


def alert(title: str, message: str = "") -> bool:
    """A finished background job reaching you: desktop toast AND a
    HUD flash when the deck is already open.

    The HUD pulse is best-effort (overlay may be closed or not yet
    started) — the toast is the guaranteed channel.
    """
    shown = toast(title, message or "")
    try:
        from system import overlay
        text = f"{title} — {message}" if message else title
        overlay.notice(text[:70])
    except Exception as exc:
        log.debug("HUD notice skipped: %s", exc)
    return shown


def toast(title: str, message: str = "", duration: int = 4) -> bool:
    """Show a native Windows notification (simple wrapper).

    Prefers windows_toasts via notify(); falls back to a PowerShell
    toast when the library is missing. duration is best-effort.
    Returns True when a toast was handed to the OS.
    """
    if notify(title, message or ""):
        return True
    if platform.system() != "Windows":
        log.info("[notify] %s — %s", title, message)
        return False
    try:
        import subprocess
        ps = (
            '[Windows.UI.Notifications.ToastNotificationManager, '
            'Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null; '
            '$template = [Windows.UI.Notifications.ToastNotificationManager]::'
            'GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); '
            f'$template.GetElementsByTagName("text")[0].AppendChild('
            f'$template.CreateTextNode("{title}")) | Out-Null; '
            f'$template.GetElementsByTagName("text")[1].AppendChild('
            f'$template.CreateTextNode("{message}")) | Out-Null; '
            '$notifier = [Windows.UI.Notifications.ToastNotificationManager]::'
            'CreateToastNotifier("JARVIS"); '
            '$notifier.Show([Windows.UI.Notifications.ToastNotification]::new($template));'
        )
        subprocess.Popen(["powershell", "-NoProfile", "-Command", ps],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return True
    except Exception as exc:
        log.debug("PowerShell toast failed: %s", exc)
        log.info("[notify] %s — %s", title, message)
        return False
