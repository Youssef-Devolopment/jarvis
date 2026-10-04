"""JARVIS floating HUD 2.0 — Alt+Space overlay.

A transparent, always-on-top command deck that works over any window
(games, IDEs, browsers):

  * glass-panel look: rounded glow border, hexagon logo, status dot
    that pulses while JARVIS is thinking, fade-in animation;
  * live header: version · mood · model (fetched from /api/info on
    every show), plus a NO KEY suffix in skills-only mode;
  * typewriter reply area (scrollable) instead of a one-line label,
    with a COPY button for the last answer;
  * quick chips: SCREEN / TIMER / TIME / OPEN / CLOSE / NOTE — the
    app chips prefill "open "/"close " so one tap + name runs it;
  * command history (Up/Down), mic dictation → auto-send;
  * drag by the header; Esc / ✕ / Alt+Space hide outright, while
    click-away only dismisses an idle, empty HUD — never mid-answer.

Thread model: hotkey threads and Flask handlers only push actions on
a queue; the Tk thread drains it (Tkinter is not thread-safe).
All server I/O happens on worker threads.

SSE: ``stitch_sse`` merges /api/command's stream into one reply and
surfaces ``error`` payloads (the 1.x bug that showed "(no reply)").
"""
from __future__ import annotations

import json
import queue
import threading
import urllib.error
import urllib.request
from logger import get_logger

log = get_logger(__name__)

# ----- geometry / palette -------------------------------------------------
W, H = 760, 404
TRANSPARENT = "#ff00ff"      # transparent color key
PANEL = "#0A101C"       # base surface (deep navy)
PANEL2 = "#0D1526"      # raised surface (reply well / bezel)
EDGE = "#00E5FF"            # primary accent (cyan)
EDGE_DIM = "#0E4A5E"        # dim accent ring
GLOW = "#123246"            # hairline / busy blink
TRACK = "#101B2E"       # chips + secondary buttons
SURF = "#0A0F1C"        # input well
TEXT = "#DCE7FA"
DIM = "#64748C"
GOOD = "#3DFFA2"
BUSY = "#FFB020"
DANGER = "#FF5C7A"
HEADER_H = 44

_actions: queue.Queue = queue.Queue()
_ready = threading.Event()
_state = {"root": None, "visible": False, "thread": None,
          "busy": 0, "history": [], "hidx": -1}
_lock = threading.Lock()


# ----- SSE stitching (pure — unit-tested) ---------------------------------
_TEXT_KEYS = ("delta", "reply", "text", "message", "content")


def stitch_sse(lines) -> str:
    """Merge an /api/command SSE stream into one reply string.

    Handles: JSON dicts with delta/reply/text/message/content, plain
    text payloads, and ``{"error": ...}`` (rendered visibly so failures
    never masquerade as "(no reply)"). Stops at [DONE]; ignores
    route/reasoning/tool_call/tool_result metadata.
    """
    parts: list[str] = []
    for raw in lines:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8", "replace")
        line = raw.strip() if isinstance(raw, str) else str(raw).strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except Exception:
            parts.append(payload)          # plain text chunk
            continue
        if isinstance(obj, dict):
            err = obj.get("error")
            if err:
                parts.append("[error] " + str(err))
                continue
            for key in _TEXT_KEYS:
                v = obj.get(key)
                if isinstance(v, str) and v:
                    parts.append(v)
                    break
        elif isinstance(obj, str) and obj:
            parts.append(obj)
    return "".join(parts).strip()


# ----- server I/O (worker threads only) -----------------------------------
def _base_url() -> str:
    try:
        from config import Settings
        s = Settings.load(require_key=False)
        return f"http://{s.host}:{s.port}"
    except Exception:
        import os
        return (f"http://{os.getenv('HOST', '127.0.0.1')}:"
                f"{os.getenv('PORT', '5000')}")


def _post_json(path: str, body: dict, timeout: int = 60) -> dict:
    req = urllib.request.Request(
        _base_url() + path, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def _command(text: str) -> str:
    req = urllib.request.Request(
        _base_url() + "/api/command",
        data=json.dumps({"text": text, "session": "overlay"}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return stitch_sse(r) or "(no reply)"
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace"))
            msg = detail.get("detail") or detail.get("type") or str(exc)
        except Exception:
            msg = str(exc)
        return f"[error] server said: {msg}"


def _listen() -> str:
    d = _post_json("/api/listen", {}, timeout=60)
    return (d.get("text") or "").strip()


def _info() -> dict:
    d = _http_get("/info")
    return {"mood": d.get("mood", "?"),
            "model": d.get("model_label") or d.get("model") or "?",
            "version": d.get("version", ""),
            "no_key": bool(d.get("no_key_mode"))}


def _header_text(info: dict) -> str:
    base = f"{info.get('mood', '?')} · {info.get('model', '?')}"
    return base + (" · NO KEY" if info.get("no_key") else "")


def _http_get(path: str, timeout: int = 15) -> dict:
    with urllib.request.urlopen(_base_url() + "/api" + path,
                                timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


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
        root.attributes("-alpha", 0.0)
        try:
            root.attributes("-transparentcolor", TRANSPARENT)
        except Exception:
            pass
        root.configure(bg=TRANSPARENT)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W}x{H}+{(sw - W) // 2}+{int(sh * 0.14)}")
        root.withdraw()

        # ---------- backdrop (rounded glow panel on transparent canvas)
        cv = tk.Canvas(root, bg=TRANSPARENT, highlightthickness=0,
                       width=W, height=H, bd=0)
        cv.pack()

        def round_rect(x1, y1, x2, y2, r, **kw):
            pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                   x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                   x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
            return cv.create_polygon(pts, smooth=True, **kw)

        # ---------- backdrop: bezel ring + accent edge
        round_rect(6, 6, W - 6, H - 6, 16, fill=PANEL2, outline=GLOW, width=1)
        round_rect(3, 3, W - 3, H - 3, 16, fill=PANEL, outline=EDGE, width=2)
        # hexagon logo (glow ring + solid mark)
        import math
        cx, cy, rr = 26, 23, 11
        outer = []
        for i in range(6):
            a = math.radians(60 * i - 30)
            outer += [cx + (rr + 3) * math.cos(a), cy + (rr + 3) * math.sin(a)]
        cv.create_polygon(outer, fill="", outline=EDGE_DIM, width=1)
        hexpts = []
        for i in range(6):
            a = math.radians(60 * i - 30)
            hexpts += [cx + rr * math.cos(a), cy + rr * math.sin(a)]
        cv.create_polygon(hexpts, fill=EDGE, outline=TEXT, width=1)
        inner = []
        for i in range(6):
            a = math.radians(60 * i - 30)
            inner += [cx + 5 * math.cos(a), cy + 5 * math.sin(a)]
        cv.create_polygon(inner, fill=PANEL)
        # header divider: dim track + bright accent segment
        cv.create_line(14, HEADER_H, W - 14, HEADER_H, fill=GLOW, width=1)
        cv.create_line(14, HEADER_H, 154, HEADER_H, fill=EDGE, width=1)
        # status dot with halo + close glyph
        cv.create_oval(W - 35, 15, W - 17, 33, outline=GLOW, width=1)
        dot = cv.create_oval(W - 32, 18, W - 20, 30, fill=GOOD, outline="")
        close_id = cv.create_text(W - 56, 23, text="✕", fill=DIM,
                                  font=("Segoe UI", 11))
        cv.tag_bind(close_id, "<Button-1>", lambda e: hide())
        cv.tag_bind(close_id, "<Enter>",
                    lambda e: cv.itemconfig(close_id, fill=DANGER))
        cv.tag_bind(close_id, "<Leave>",
                    lambda e: cv.itemconfig(close_id, fill=DIM))

        # ---------- header labels
        def label(x, y, anchor, **kw):
            w = tk.Label(cv, bg=kw.pop("bg", PANEL), **kw)
            cv.create_window(x, y, window=w, anchor=anchor)
            return w

        title = label(48, 23, "w", text="J A R V I S", fg="#FFFFFF",
                      font=("Bahnschrift", 12, "bold"))
        ver = label(152, 23, "w", text="", fg=DIM,
                    font=("Bahnschrift", 9))
        hdr = label(W - 76, 23, "e", text="", fg=TEXT,
                    font=("Bahnschrift", 9), bg="#101B2E", padx=9, pady=3,
                    highlightthickness=1, highlightbackground=EDGE_DIM)

        # ---------- reply area (accent bar + readable prose font)
        reply_wrap = tk.Frame(cv, bg=PANEL2, highlightbackground=GLOW,
                              highlightthickness=1)
        cv.create_window(14, 50, window=reply_wrap, anchor="nw",
                         width=W - 28, height=218)
        tk.Frame(reply_wrap, bg=EDGE, width=3).pack(side="left", fill="y")
        reply = tk.Text(reply_wrap, bg=PANEL2, fg=TEXT, relief="flat",
                        font=("Segoe UI", 11), wrap="word", state="disabled",
                        insertbackground=EDGE, padx=12, pady=8,
                        spacing1=2, spacing3=2,
                        selectbackground=EDGE, selectforeground="#000")
        rscroll = tk.Scrollbar(reply_wrap, command=reply.yview,
                               bg=PANEL2, troughcolor=PANEL2,
                               activebackground=EDGE, width=8)
        reply.configure(yscrollcommand=rscroll.set)
        rscroll.pack(side="right", fill="y")
        reply.pack(side="left", fill="both", expand=True)

        def set_reply(text, color=TEXT):
            reply.configure(state="normal")
            reply.delete("1.0", "end")
            reply.insert("1.0", text)
            reply.configure(state="disabled", fg=color)
            reply.yview("end")

        def append_reply(text):
            reply.configure(state="normal")
            reply.insert("end", text)
            reply.configure(state="disabled")
            reply.yview("end")

        # ---------- chips (hover-reactive pills)
        chips = tk.Frame(cv, bg=PANEL)
        cv.create_window(14, 280, window=chips, anchor="nw")

        def chip(text, cmd):
            b = tk.Button(chips, text=text, command=cmd, bg=TRACK,
                          fg="#9FB6D8", activebackground=EDGE,
                          activeforeground="#000", relief="flat",
                          font=("Bahnschrift", 9, "bold"), padx=10, pady=3,
                          cursor="hand2", bd=0,
                          highlightthickness=1, highlightbackground="#1A2A44",
                          disabledforeground=DIM)
            b.pack(side="left", padx=(0, 6))
            b.bind("<Enter>", lambda e, w=b: w.configure(bg="#16283F",
                                                         fg=EDGE))
            b.bind("<Leave>", lambda e, w=b: w.configure(bg=TRACK,
                                                         fg="#9FB6D8"))
            return b

        hint = tk.Label(cv, bg=PANEL, fg=DIM, font=("Bahnschrift", 8),
                        text="Enter ↵ send · ↑↓ history · Esc hide")
        cv.create_window(W - 14, 292, window=hint, anchor="e")

        # ---------- input row (border lights up on focus)
        input_wrap = tk.Frame(cv, bg=EDGE_DIM)
        cv.create_window(14, 316, window=input_wrap, anchor="nw",
                         height=38, width=W - 28)
        entry = tk.Entry(input_wrap, bg=SURF, fg=TEXT,
                         insertbackground=EDGE, relief="flat",
                         font=("Consolas", 11), bd=4,
                         insertwidth=2, highlightbackground=EDGE_DIM)
        entry.pack(side="left", fill="both", expand=True, ipady=4)
        entry.bind("<FocusIn>",
                   lambda e: input_wrap.configure(bg=EDGE))
        entry.bind("<FocusOut>",
                   lambda e: input_wrap.configure(bg=EDGE_DIM))

        def button(parent, text, cmd, w=8, primary=False):
            b = tk.Button(parent, text=text, command=cmd,
                          bg=("#0C2E44" if primary else TRACK),
                          fg=("#CFFAFF" if primary else TEXT),
                          activebackground=EDGE,
                          activeforeground="#000", relief="flat",
                          font=("Bahnschrift", 9, "bold"), width=w,
                          cursor="hand2", bd=0,
                          highlightthickness=1, highlightbackground="#1A2A44",
                          disabledforeground=DIM)
            b.pack(side="left", padx=(8, 0), fill="y")
            hot = "#12425C" if primary else "#16283F"
            b.bind("<Enter>", lambda e, v=hot: b.configure(bg=v))
            b.bind("<Leave>", lambda e: b.configure(
                bg=("#0C2E44" if primary else TRACK)))
            return b

        send_btn = button(input_wrap, "SEND", lambda: None, w=7,
                          primary=True)
        mic_btn = button(input_wrap, "MIC", lambda: None, w=5)

        # ---------- footer / status line
        status_lbl = label(14, 372, "nw", text="ready · Alt+Space",
                           fg=DIM, font=("Bahnschrift", 8))

        def copy_reply():
            try:
                text = reply.get("1.0", "end").strip()
            except Exception:
                text = ""
            if not text:
                return
            try:
                root.clipboard_clear()
                root.clipboard_append(text)
                status_lbl.configure(text="copied · Alt+Space", fg=GOOD)
            except Exception as exc:
                log.warning("overlay copy failed: %s", exc)

        copy_btn = tk.Button(cv, text="⧉ COPY", command=copy_reply,
                             bg=TRACK, fg=DIM, activebackground=EDGE,
                             activeforeground="#000", relief="flat",
                             font=("Bahnschrift", 8, "bold"), padx=8, pady=1,
                             cursor="hand2", bd=0, highlightthickness=1,
                             highlightbackground="#1A2A44")
        copy_btn.bind("<Enter>", lambda e: copy_btn.configure(fg=EDGE))
        copy_btn.bind("<Leave>", lambda e: copy_btn.configure(fg=DIM))
        cv.create_window(W - 14, 372, window=copy_btn, anchor="e")

        # ---------- state
        busy = {"n": 0}
        type_job = {"id": None}
        drag = {"x": 0, "y": 0}

        def hide():
            if not _state["visible"]:
                return
            _state["visible"] = False
            try:
                def out(a=0.97):
                    try:
                        if _state["visible"]:
                            return      # re-shown mid-fade: abort
                        a = max(0.0, a - 0.19)
                        root.attributes("-alpha", a)
                        if a > 0:
                            root.after(15, lambda: out(a))
                        else:
                            root.withdraw()
                    except Exception:
                        pass
                out()
            except Exception:
                pass

        def fade_in():
            root.deiconify()
            root.lift()
            root.attributes("-topmost", True)
            _state["visible"] = True
            try:
                x, y = root.winfo_x(), root.winfo_y()
            except Exception:
                x = y = 0
            slide = x >= 0 and y >= 0

            def step(a=0.0):
                try:
                    if not _state["visible"]:
                        return
                    a = min(0.97, a + 0.16)
                    root.attributes("-alpha", a)
                    off = int(12 * (1 - a / 0.97)) if slide else 0
                    root.geometry(f"{W}x{H}+{x}+{y + off}")
                    if a < 0.97:
                        root.after(16, lambda: step(a))
                    else:
                        root.geometry(f"{W}x{H}+{x}+{y}")
                except Exception:
                    pass
            step()
            root.focus_force()
            entry.focus_set()

        def set_busy(on):
            busy["n"] = 1 if on else 0
            try:
                send_btn.configure(state="disabled" if on else "normal")
                mic_btn.configure(state="disabled" if on else "normal")
            except Exception:
                pass

        def pulse():
            """Blink the status dot while busy, solid green when idle."""
            try:
                if busy["n"]:
                    cur = cv.itemcget(dot, "fill")
                    cv.itemconfig(dot, fill=GLOW if cur == BUSY else BUSY)
                else:
                    cv.itemconfig(dot, fill=GOOD)
                root.after(350, pulse)
            except Exception:
                pass

        def type_out(text, color=TEXT):
            """Typewriter reveal of the reply."""
            if type_job["id"]:
                try:
                    root.after_cancel(type_job["id"])
                except Exception:
                    pass
                type_job["id"] = None
            set_reply("", color)
            total = len(text)
            if total == 0:
                return
            chunk = max(2, total // 70)
            pos = {"i": 0}

            def tick():
                pos["i"] = min(total, pos["i"] + chunk)
                set_reply(text[:pos["i"]], color)
                if pos["i"] < total:
                    type_job["id"] = root.after(24, tick)
                else:
                    type_job["id"] = None
            tick()

        # ---------- actions (called from workers via queue)
        def submit(event=None):
            text = entry.get().strip()
            if not text or busy["n"]:
                return "break"
            _state["history"].append(text)
            _state["hidx"] = len(_state["history"])
            entry.delete(0, "end")
            set_busy(True)
            set_reply("… thinking", DIM)
            threading.Thread(target=_worker, args=("cmd", text),
                             daemon=True).start()
            return "break"

        def mic():
            if busy["n"]:
                return
            set_busy(True)
            set_reply("… listening", DIM)
            threading.Thread(target=_worker, args=("mic", ""),
                             daemon=True).start()

        def history_move(delta):
            h = _state["history"]
            if not h:
                return
            i = _state["hidx"] + delta
            i = max(0, min(len(h), i))
            _state["hidx"] = i
            entry.delete(0, "end")
            if i < len(h):
                entry.insert(0, h[i])

        def _worker(kind, payload):
            try:
                if kind == "cmd":
                    reply_txt = _command(payload)
                else:
                    heard = _listen()
                    if heard:
                        _actions.put(("heard", heard))
                        reply_txt = _command(heard)
                    else:
                        reply_txt = "didn't catch that."
                _actions.put(("result", reply_txt))
            except Exception as exc:
                _actions.put(("result", f"[error] {exc}"))

        # ---------- chips wiring
        def _quick(text):
            if busy["n"]:
                return
            entry.delete(0, "end")
            entry.insert(0, text)
            submit()

        chip("▣ SCREEN", lambda: _quick("what's on my screen"))
        chip("◷ TIMER 5M", lambda: _quick("set a timer for 5 minutes"))
        chip("◷ TIME", lambda: _quick("what time is it"))
        chip("＋ OPEN", lambda: (entry.delete(0, "end"),
                                entry.insert(0, "open "),
                                entry.focus_set()))
        chip("✕ CLOSE", lambda: (entry.delete(0, "end"),
                                 entry.insert(0, "close "),
                                 entry.focus_set()))
        chip("✎ NOTE", lambda: (entry.delete(0, "end"),
                                entry.insert(0, "remember: "),
                                entry.focus_set()))

        # ---------- key bindings
        entry.bind("<Return>", submit)
        entry.bind("<Up>", lambda e: (history_move(-1), "break")[1])
        entry.bind("<Down>", lambda e: (history_move(+1), "break")[1])
        root.bind("<Escape>", lambda e: hide())

        def on_focus_out(event):
            # Click-away hides an untouched HUD, but never yanks it
            # mid-thought: a pending answer or half-typed command keeps
            # the window up (Esc / ✕ / Alt+Space still hide outright).
            if busy["n"]:
                return
            try:
                composing = bool(entry.get().strip())
            except Exception:
                composing = False
            if composing:
                return
            root.after(250, lambda: (root.focus_displayof() is None)
                       and _state["visible"] and hide())
        root.bind("<FocusOut>", on_focus_out)

        # ---------- drag by header
        def drag_start(event):
            drag["x"] = event.x_root - root.winfo_x()
            drag["y"] = event.y_root - root.winfo_y()

        def drag_move(event):
            root.geometry(f"+{event.x_root - drag['x']}"
                          f"+{event.y_root - drag['y']}")

        cv.bind("<Button-1>", lambda e: (e.y < HEADER_H and drag_start(e)))
        cv.bind("<B1-Motion>", lambda e: (e.y < HEADER_H and drag_move(e)))

        # ---------- queue pump
        def on_result(text, color=TEXT):
            set_busy(False)
            type_out(text, color)
            status_lbl.configure(
                text=("error" if text.startswith("[error]") else "done")
                + " · Alt+Space to recall", fg=(DANGER if
                                                 text.startswith("[error]")
                                                 else DIM))

        def pump():
            # NEVER dies: one poisoned action must not disable the HUD
            # (the thread stays alive, so ensure_started would keep
            # queueing into a pump that no longer runs — silent no-op).
            try:
                while True:
                    kind, payload = _actions.get_nowait()
                    try:
                        if kind == "result":
                            on_result(payload,
                                      DANGER if payload.startswith("[error]")
                                      else TEXT)
                        elif kind == "heard":
                            set_reply(f"🎙 heard: {payload}", DIM)
                        elif kind == "info":
                            ver.configure(
                                text=f"v{payload.get('version','')}")
                            hdr.configure(text=_header_text(payload))
                        elif kind == "show":
                            fade_in()
                            threading.Thread(target=_pull_info,
                                             daemon=True).start()
                        elif kind == "hide":
                            hide()
                        elif kind == "toggle":
                            if _state["visible"]:
                                hide()
                            else:
                                fade_in()
                                threading.Thread(target=_pull_info,
                                                 daemon=True).start()
                        elif kind == "quit":
                            root.destroy()
                            return
                    except Exception as exc:
                        log.warning("overlay action %r failed: %s",
                                    kind, exc)
            except queue.Empty:
                pass
            except Exception as exc:
                log.warning("overlay pump error: %s", exc)
            try:
                root.after(80, pump)
            except Exception:
                pass        # root destroyed — stop rescheduling

        def _pull_info():
            try:
                _actions.put(("info", _info()))
            except Exception:
                pass

        send_btn.configure(command=submit)
        mic_btn.configure(command=mic)

        _state["root"] = root
        # Tk callback errors normally go to stderr — invisible under
        # pythonw and fatal to mainloop. Log them instead.
        root.report_callback_exception = (
            lambda *a: log.warning("overlay tk callback error: %s", a[1]))
        _ready.set()
        pulse()
        pump()
        try:
            root.mainloop()
        except Exception as exc:
            log.warning("overlay mainloop ended: %s", exc)
        finally:
            _state["visible"] = False
    except Exception as exc:
        log.warning("Overlay thread failed: %s", exc)
        _ready.set()


# ----- public API ---------------------------------------------------------
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


def _pref_enabled() -> bool:
    try:
        from memory import get_pref
        return bool(get_pref("overlay_enabled", True))
    except Exception:
        return True


def toggle() -> None:
    """Called from the global hotkey (any thread)."""
    if not _pref_enabled():
        return
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
