"""Alt+Space floating HUD — a transparent, always-on-top command overlay.

Design goals:
  * appears over any active window (games, IDEs, browsers), auto-hides
    on blur / Esc / second Alt+Space press;
  * zero cost until first use — the Tk thread starts lazily on the
    first toggle;
  * fully thread-safe — hotkey threads push actions onto a queue that
    the Tk thread drains (Tkinter is not thread-safe).

The HUD talks to the local Flask API only (127.0.0.1), so it works
exactly like the dashboard: POST /api/command (SSE) and /api/listen.
"""
from __future__ import annotations

import json
import queue
import threading
import urllib.request
from logger import get_logger

log = get_logger(__name__)

# ----- geometry / palette -------------------------------------------------
W, H = 560, 132
BG = "#ff00ff"          # transparentcolor key (magenta is fully keyed out)
FRAME = "#0a0e17"
EDGE = "#00e5ff"
TEXT = "#c9d6e8"
DIM = "#5b6b82"

_actions: queue.Queue = queue.Queue()
_ready = threading.Event()
_state = {"root": None, "visible": False, "thread": None}
_lock = threading.Lock()


# ----- server I/O (worker thread only) ------------------------------------
def _base_url() -> str:
    from config import get_settings
    s = get_settings()
    return f"http://{s.host}:{s.port}"


def _post_json(path: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        _base_url() + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _command(text: str) -> str:
    """POST /api/command and stitch the SSE stream back into one reply."""
    req = urllib.request.Request(
        _base_url() + "/api/command",
        data=json.dumps({"text": text, "session": "overlay"}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    parts: list[str] = []
    with urllib.request.urlopen(req, timeout=90) as r:
        for raw in r:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            try:
                obj = json.loads(payload)
            except Exception:
                parts.append(payload)   # plain text chunk
                continue
            if isinstance(obj, dict):
                for key in ("delta", "reply", "text", "source"):
                    if obj.get(key) and key != "source":
                        parts.append(str(obj[key]))
                        break
    return "".join(parts).strip() or "(no reply)"


def _listen() -> str:
    d = _post_json("/api/listen", {}, timeout=60)
    return (d.get("text") or "").strip()


# ----- Tk thread ----------------------------------------------------------
def _run() -> None:
    try:
        import tkinter as tk
    except Exception as exc:
        log.warning("Overlay unavailable (tkinter: %s)", exc)
        _ready.set()
        return
    try:
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", BG)
        except Exception:
            pass
        root.configure(bg=BG)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw - W) // 2}+{int(sh * 0.16)}")
        root.withdraw()

        frame = tk.Frame(root, bg=FRAME, highlightbackground=EDGE,
                         highlightthickness=1, bd=0)
        frame.pack(fill="both", expand=True, padx=1, pady=1)

        title = tk.Label(frame, text="  ◆ JARVIS OVERLAY   Alt+Space",
                         bg=FRAME, fg=EDGE, anchor="w",
                         font=("Consolas", 9))
        title.pack(fill="x", padx=10, pady=(7, 0))

        row = tk.Frame(frame, bg=FRAME)
        row.pack(fill="x", padx=10, pady=6)

        entry = tk.Entry(row, bg="#121a2b", fg=TEXT, insertbackground=EDGE,
                         relief="flat", font=("Consolas", 11))
        entry.pack(side="left", fill="x", expand=True, ipady=6)

        def btn(text, cmd):
            b = tk.Button(row, text=text, command=cmd, bg="#16233a", fg=TEXT,
                          activebackground=EDGE, activeforeground="#000",
                          relief="flat", font=("Consolas", 9, "bold"),
                          padx=8, pady=5, cursor="hand2")
            b.pack(side="left", padx=(6, 0))
            return b

        out = tk.Label(frame, text="Ask anything — Enter to send, Esc to hide.",
                       bg=FRAME, fg=DIM, anchor="w", font=("Consolas", 9),
                       wraplength=W - 30, justify="left")
        out.pack(fill="x", padx=10, pady=(0, 7))

        busy = {"n": 0}

        def hide():
            _state["visible"] = False
            root.withdraw()

        def set_out(text, color=TEXT):
            out.configure(text=text[:300], fg=color)

        def _worker(kind: str, payload: str) -> None:
            try:
                if kind == "cmd":
                    reply = _command(payload)
                else:
                    heard = _listen()
                    reply = _command(heard) if heard else "didn't catch that."
                _actions.put(("result", reply))
            except Exception as exc:
                _actions.put(("result", f"[error] {exc}"))

        def submit(event=None):
            text = entry.get().strip()
            if not text or busy["n"]:
                return
            busy["n"] += 1
            entry.delete(0, "end")
            set_out("… thinking", DIM)
            threading.Thread(target=_worker, args=("cmd", text),
                             daemon=True).start()

        def mic():
            if busy["n"]:
                return
            busy["n"] += 1
            set_out("… listening", DIM)
            threading.Thread(target=_worker, args=("mic", ""),
                             daemon=True).start()

        def on_result(reply: str):
            busy["n"] = max(0, busy["n"] - 1)
            set_out(reply, TEXT)

        entry.bind("<Return>", submit)
        entry.bind("<Escape>", lambda e: hide())
        frame.bind("<Escape>", lambda e: hide())
        root.bind("<Escape>", lambda e: hide())

        def on_focus_out(event):
            # grace period so button presses inside the HUD survive
            root.after(250, lambda: (root.focus_displayof() is None) and hide())

        root.bind("<FocusOut>", on_focus_out)

        btn("SEND", submit)
        btn("MIC", mic)
        btn("✕", hide)

        def pump():
            try:
                while True:
                    kind, payload = _actions.get_nowait()
                    if kind == "result":
                        on_result(payload)
                    elif kind == "show":
                        root.deiconify()
                        root.lift()
                        root.attributes("-topmost", True)
                        root.focus_force()
                        entry.focus_set()
                        _state["visible"] = True
                    elif kind == "hide":
                        hide()
                    elif kind == "quit":
                        root.destroy()
                        return
                    elif kind == "toggle":
                        if _state["visible"]:
                            hide()
                        else:
                            root.deiconify()
                            root.lift()
                            root.attributes("-topmost", True)
                            root.focus_force()
                            entry.focus_set()
                            _state["visible"] = True
            except queue.Empty:
                pass
            root.after(80, pump)

        _state["root"] = root
        _ready.set()
        pump()
        root.mainloop()
    except Exception as exc:
        log.warning("Overlay thread failed: %s", exc)
        _ready.set()


def ensure_started() -> bool:
    """Lazily spawn the Tk thread once. Returns True when ready."""
    with _lock:
        if _state["thread"] and _state["thread"].is_alive():
            return _ready.wait(timeout=5)
        _ready.clear()
        t = threading.Thread(target=_run, daemon=True, name="jarvis-overlay")
        _state["thread"] = t
        t.start()
    return _ready.wait(timeout=8)


def toggle() -> None:
    """Called from the global hotkey (any thread)."""
    try:
        from memory import get_pref
        if not get_pref("overlay_enabled", True):
            return
    except Exception:
        pass
    if ensure_started():
        _actions.put(("toggle", ""))
    else:
        log.info("Overlay thread did not come up")


def show() -> None:
    if ensure_started():
        _actions.put(("show", ""))


def hide() -> None:
    if _state["root"]:
        _actions.put(("hide", ""))
