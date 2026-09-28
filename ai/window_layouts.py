"""Window layouts — save and restore window positions."""

from __future__ import annotations
import json, platform, time
from logger import get_logger

log = get_logger(__name__)
IS_WIN = platform.system() == "Windows"


def _list_windows():
    if not IS_WIN: return []
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        out = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd): return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0: return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if not title.strip(): return True
            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            out.append({"title": title[:200], "x": rect.left, "y": rect.top,
                        "w": rect.right - rect.left, "h": rect.bottom - rect.top})
            return True
        user32.EnumWindows(cb, 0)
        return out
    except Exception as exc:
        log.warning("list_windows failed: %s", exc)
        return []


def save(name):
    if not name: return {"ok": False, "error": "no name"}
    windows = _list_windows()
    from memory import save_layout
    ok = save_layout(name, json.dumps(windows, ensure_ascii=False))
    return {"ok": ok, "count": len(windows), "name": name}


def restore(name):
    from memory import get_layout
    raw = get_layout(name)
    if not raw: return {"ok": False, "error": f"layout '{name}' not found"}
    try:
        saved = json.loads(raw)
    except Exception:
        return {"ok": False, "error": "bad layout data"}

    if not IS_WIN:
        return {"ok": False, "error": "not windows"}

    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    restored = 0

    for s in saved:
        title = s.get("title", "")
        if not title: continue
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(hwnd, lparam):
            if not user32.IsWindowVisible(hwnd): return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0: return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title.lower()[:40] in buf.value.lower():
                found.append(hwnd)
                return False
            return True
        user32.EnumWindows(cb, 0)
        if found:
            hwnd = found[0]
            user32.ShowWindow(hwnd, 9)
            user32.MoveWindow(hwnd, s["x"], s["y"], s["w"], s["h"], True)
            restored += 1
            time.sleep(0.15)

    return {"ok": True, "restored": restored, "total": len(saved), "name": name}


def list_layouts():
    from memory import list_layouts as _list
    return _list()


def delete(name):
    from memory import delete_layout
    return delete_layout(name)
