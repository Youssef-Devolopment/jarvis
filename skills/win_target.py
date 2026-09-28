"""Native Windows control targeting via pywinauto (UIA tree).

Clicks real buttons and types into real fields by name — far more
reliable than pixel coordinates. Gated by Code Mode + desktop_control.

COM note: pywinauto/comtypes must initialize COM on a fresh thread —
the main thread may already carry an incompatible apartment (e.g. set
via the audio stack at boot). Every operation therefore runs inside a
short-lived worker thread; results come back as plain strings.
"""
from __future__ import annotations
import concurrent.futures
import re
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_TIMEOUT = 60


def _gate() -> str:
    try:
        from memory import get_pref
        if not get_pref("code_mode_enabled", False):
            return "Code Mode is off — enable it first."
        if not get_pref("desktop_control_enabled", True):
            return "Desktop control is disabled in prefs."
    except Exception:
        return "Could not read prefs."
    return ""


def _run_worker(fn, *args) -> str:
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="uia") as ex:
        try:
            return ex.submit(fn, *args).result(timeout=_TIMEOUT)
        except concurrent.futures.TimeoutError:
            return "Timed out talking to the window."
        except Exception as exc:
            return f"Control failed: {str(exc)[:150]}"


def _do_click(window: str, control: str) -> str:
    try:
        import pywinauto  # noqa: F401  (fresh thread: clean COM apartment)
        from pywinauto import Desktop
    except ImportError:
        return "Native control needs pywinauto. Run: pip install pywinauto"
    try:
        d = Desktop(backend="uia").window(
            title_re=f".*{re.escape(window)}.*")
        if not d.exists(timeout=5):
            return f"No window matching '{window}'."
        d.set_focus()
        d.child_window(
            title_re=f".*{re.escape(control)}.*").click_input()
        log.info("win_click: %r in %r", control, window)
        return f"Clicked '{control}'."
    except Exception as exc:
        log.warning("win_click failed: %s", exc)
        return f"Could not click '{control}': {str(exc)[:120]}"


def _do_type(window: str, control: str, text: str) -> str:
    try:
        import pywinauto  # noqa: F401
        from pywinauto import Desktop
    except ImportError:
        return "Native control needs pywinauto. Run: pip install pywinauto"
    try:
        d = Desktop(backend="uia").window(
            title_re=f".*{re.escape(window)}.*")
        if not d.exists(timeout=5):
            return f"No window matching '{window}'."
        d.set_focus()
        ctl = d.child_window(title_re=f".*{re.escape(control)}.*")
        try:
            ctl.set_edit_text(text)
        except Exception:
            ctl.click_input()
            ctl.type_keys(text, with_spaces=True)
        log.info("win_type: %d chars into %r", len(text), control)
        return f"Typed into '{control}'."
    except Exception as exc:
        log.warning("win_type failed: %s", exc)
        return f"Could not type into '{control}': {str(exc)[:120]}"


def win_click(window: str, control: str) -> str:
    err = _gate()
    if err:
        return err
    return _run_worker(_do_click, window, control)


def win_type(window: str, control: str, text: str) -> str:
    err = _gate()
    if err:
        return err
    return _run_worker(_do_type, window, control, text)


@register("win_click", [
    r"^(?:click(?:\s+the)?)\s+(?P<ctrl>.+?)\s+(?:button\s+)?in\s+(?P<win>.+?)[\?\.\!]?$",
    r"^(?:press(?:\s+the)?)\s+(?P<ctrl>.+?)(?:\s+in\s+(?P<win>.+?))?[\?\.\!]?$",
], "Click a named button/control")
def s_win_click(text, m):
    ctrl = (m.group("ctrl") or "").strip()
    win = (m.groupdict().get("win") or "").strip() or ".*"
    if not ctrl:
        return None
    return win_click(win, ctrl)


@register("win_type", [
    r"^type\s+[\"']?(?P<text>.+?)[\"']?\s+into\s+(?P<ctrl>.+?)\s+in\s+(?P<win>.+?)[\?\.\!]?$",
], "Type text into a named field")
def s_win_type(text, m):
    t = (m.group("text") or "").strip()
    if not t:
        return None
    return win_type((m.group("win") or "").strip(),
                    (m.group("ctrl") or "").strip(), t)
