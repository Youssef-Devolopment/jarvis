"""JARVIS floating HUD 4.0 — Glass Command Deck (Alt+Space overlay).

Rebuilt from zero: a rounded, transparent-cornered command deck that
floats over any window (games, IDEs, browsers):

  * true transparent corners (Windows transparentcolor key) around a
    20px-radius double bezel with a top accent line — no OS blur,
    DPI-aware native rendering;
  * two modes: a compact input deck (header + prompt + chips + footer)
    that expands into a full deck with a scrollable reply well;
  * live header: JARVIS title, version · mood · model, status dot
    (green idle / amber pulse while thinking / red on error),
    refreshed on every show, after every answer and ~10s while visible;
  * typewriter reply area with a COPY button for the last answer;
  * quick chips: SCREEN / TIMER / TIME / OPEN / CLOSE / NOTE — the
    app chips prefill "open "/"close " so one tap + name runs it;
  * command history (Up/Down), mic dictation → auto-send;
  * drag by the header; Esc / ✕ / Alt+Space hide outright, while
    focus-away only dismisses an idle, empty HUD — never mid-answer.

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
W = 760                       # deck width
INPUT_H = 200                  # compact deck height
EXP_H = 424                    # expanded deck height (with reply well)
RADIUS = 20                    # corner radius
REFRESH_TICKS = 125            # pump runs ~80ms: refresh header ~10s
TRANSPARENT = "#ff00ff"        # transparent color key
PANEL = "#0A101C"              # base surface (deep navy)
PANEL2 = "#0D1526"             # raised surface (reply well / bezel)
EDGE = "#00E5FF"               # primary accent (cyan)
EDGE_DIM = "#0E4A5E"           # dim accent ring
GLOW = "#123246"               # hairline / busy blink
TRACK = "#101B2E"              # chips + secondary buttons
SURF = "#0A0F1C"               # input well
TEXT = "#DCE7FA"
DIM = "#64748C"
HINT = "#475569"
GOOD = "#3DFFA2"
BUSY = "#FFB020"
DANGER = "#FF5C7A"

_actions: queue.Queue = queue.Queue()
_ready = threading.Event()
_state = {"root": None, "visible": False, "thread": None,
          "busy": 0, "history": [], "hidx": -1}
_lock = threading.Lock()


# ----- SSE stitching (pure — unit-tested) ---------------------------------
_TEXT_KEYS = ("delta", "reply", "text", "message", "content")
_DONE = object()                       # sentinel: end of stream


def _sse_piece(raw) -> object:
    """One SSE line -> reply piece, '[error] ...', _DONE, or None.

    None means "metadata / not a reply" (route, reasoning, tool_call…).
    """
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    line = raw.strip() if isinstance(raw, str) else str(raw).strip()
    if not line.startswith("data:"):
        return None
    payload = line[5:].strip()
    if payload == "[DONE]":
        return _DONE
    try:
        obj = json.loads(payload)
    except Exception:
        return payload                  # plain text chunk
    if isinstance(obj, dict):
        err = obj.get("error")
        if err:
            return "[error] " + str(err)
        for key in _TEXT_KEYS:
            v = obj.get(key)
            if isinstance(v, str) and v:
                return v
        return None
    if isinstance(obj, str) and obj:
        return obj
    return None


def _stream_from(lines):
    """Yield reply pieces from an SSE response (any line iterable)."""
    for raw in lines:
        piece = _sse_piece(raw)
        if piece is _DONE:
            return
        if piece:
            yield piece


def stitch_sse(lines) -> str:
    """Merge an /api/command SSE stream into one reply string.

    Handles: JSON dicts with delta/reply/text/message/content, plain
    text payloads, and ``{"error": ...}`` (rendered visibly so failures
    never masquerade as "(no reply)"). Stops at [DONE]; ignores
    route/reasoning/tool_call/tool_result metadata.
    """
    return "".join(_stream_from(lines)).strip()


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


def _command_stream(text: str):
    """Yield reply pieces from /api/command as they arrive (live)."""
    req = urllib.request.Request(
        _base_url() + "/api/command",
        data=json.dumps({"text": text, "session": "overlay"}).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            yield from _stream_from(r)
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8", "replace"))
            msg = detail.get("detail") or detail.get("type") or str(exc)
        except Exception:
            msg = str(exc)
        yield f"[error] server said: {msg}"


def _command(text: str) -> str:
    return "".join(_command_stream(text)).strip() or "(no reply)"


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


def _pull_info() -> None:
    """Refresh mood/model/version onto the deck (worker thread)."""
    try:
        _actions.put(("info", _info()))
    except Exception:
        pass


# Quick chips, data-driven (label, kind, payload):
# kind "send" fires immediately, kind "fill" pre-fills the input.
CHIPS = (
    ("▣ SCREEN", "send", "what's on my screen"),
    ("◷ TIMER 5M", "send", "set a timer for 5 minutes"),
    ("◷ TIME", "send", "what time is it"),
    ("＋ OPEN", "fill", "open "),
    ("✕ CLOSE", "fill", "close "),
    ("✎ NOTE", "fill", "remember: "),
)


# ----- Tk thread ----------------------------------------------------------
def _run() -> None:
    try:
        import tkinter as tk
    except Exception as exc:
        log.warning("Overlay unavailable (tkinter: %s)", exc)
        _ready.set()
        return
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass
    except Exception:
        pass

    def _layout(expanded: bool) -> dict:
        """Vertical layout per mode (y of each content group)."""
        if expanded:
            return {"reply": 62, "input": 290, "chips": 346,
                    "footer": 388, "h": EXP_H}
        return {"reply": None, "input": 62, "chips": 118,
                "footer": 160, "h": INPUT_H}

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
        x0, y0 = (sw - W) // 2, int(sh * 0.10)
        root.geometry(f"{W}x{INPUT_H}+{x0}+{y0}")
        root.withdraw()

        # ---------- backdrop (rounded glass panel on transparent canvas)
        cv = tk.Canvas(root, bg=TRANSPARENT, highlightthickness=0,
                       width=W, height=EXP_H, bd=0)
        cv.pack()

        def round_rect(x1, y1, x2, y2, r, **kw):
            pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
                   x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
                   x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
            return cv.create_polygon(pts, smooth=True, **kw)

        mode = {"expanded": False}
        groups: dict = {}          # group name -> [canvas item ids]
        interactive = []           # canvas ids that must not start drags

        def draw_chrome(expanded: bool):
            cv.delete("chrome")
            h = _layout(expanded)["h"]
            # outer halo hairline, inner raised surface
            round_rect(5, 5, W - 5, h - 5, RADIUS, fill=PANEL2,
                       outline=GLOW, width=1, tags="chrome")
            round_rect(2, 2, W - 2, h - 2, RADIUS - 2, fill=PANEL,
                       outline=EDGE_DIM, width=2, tags="chrome")
            # top accent line: bright segment fading into the hairline
            cv.create_line(40, 3, W - 40, 3, fill=EDGE, width=2,
                           tags="chrome")
            cv.create_line(16, 3, 40, 3, fill=EDGE_DIM, width=2,
                           tags="chrome")
            cv.create_line(W - 40, 3, W - 16, 3, fill=EDGE_DIM, width=2,
                           tags="chrome")
            # separator under the header
            cv.create_line(14, 52, W - 14, 52, fill=GLOW, width=1,
                           tags="chrome")
            if expanded:
                cv.create_line(14, 52, 174, 52, fill=EDGE, width=1,
                               tags="chrome")

        # ---------- header: hexagon mark + title + live header text
        import math
        cx, cy, rr = 30, 29, 10
        for ring, rad, fill, out in ((rr + 3, rr + 3, "", EDGE_DIM),
                                     (rr, rr, EDGE, TEXT),
                                     (5, 5, PANEL, "")):
            pts = []
            for i in range(6):
                a = math.radians(60 * i - 30)
                pts += [cx + rad * math.cos(a), cy + rad * math.sin(a)]
            cv.create_polygon(pts, fill=fill, outline=out, width=1)

        cv.create_text(52, 29, text="JARVIS", anchor="w", fill=TEXT,
                       font=("Bahnschrift", 12, "bold"))
        hdr = tk.Label(cv, text="", bg=PANEL, fg=TEXT,
                       font=("Bahnschrift", 9), padx=8, pady=1,
                       highlightthickness=1,
                       highlightbackground=EDGE_DIM)
        hdr_win = cv.create_window(140, 29, window=hdr, anchor="w")
        ver = tk.Label(cv, text="", bg=PANEL, fg=DIM,
                       font=("Bahnschrift", 8))
        ver_win = cv.create_window(W - 44, 29, window=ver, anchor="e")

        # status dot (halo + core) right before the version
        dot_x, dot_y = W - 170, 29
        dot_halo = cv.create_oval(dot_x - 10, dot_y - 10,
                                  dot_x + 10, dot_y + 10,
                                  outline=GLOW, width=1)
        dot_core = cv.create_oval(dot_x - 5, dot_y - 5,
                                  dot_x + 5, dot_y + 5,
                                  fill=GOOD, outline="")
        close_id = cv.create_text(W - 16, 29, text="\u2715", fill=DIM,
                                  font=("Segoe UI", 11))
        cv.tag_bind(close_id, "<Button-1>", lambda e: _hide_now())
        cv.tag_bind(close_id, "<Enter>",
                    lambda e: cv.itemconfig(close_id, fill=DANGER))
        cv.tag_bind(close_id, "<Leave>",
                    lambda e: cv.itemconfig(close_id, fill=DIM))
        interactive.append(close_id)

        # ---------- reply well (expanded mode only)
        reply_wrap = tk.Frame(cv, bg=PANEL2)
        reply_win = cv.create_window(14, 62, window=reply_wrap,
                                     anchor="nw", width=W - 28, height=214,
                                     state="hidden")
        tk.Frame(reply_wrap, bg=EDGE, width=3).pack(side="left", fill="y")
        reply = tk.Text(reply_wrap, bg=PANEL2, fg=TEXT, relief="flat",
                        font=("Segoe UI", 12), wrap="word", state="disabled",
                        insertbackground=EDGE, padx=12, pady=8,
                        spacing1=2, spacing3=2, highlightthickness=0,
                        selectbackground=EDGE, selectforeground="#000")
        rscroll = tk.Scrollbar(reply_wrap, command=reply.yview,
                               bg=PANEL2, troughcolor=PANEL2,
                               activebackground=EDGE, width=8)
        reply.configure(yscrollcommand=rscroll.set)
        reply.pack(side="left", fill="both", expand=True)
        rscroll.pack(side="right", fill="y")
        groups["reply"] = [reply_win]

        # ---------- input row: prompt + entry + mic + send
        in_y = _layout(False)["input"]
        prompt = cv.create_text(24, in_y + 20, text="\u203a", fill=EDGE,
                                font=("Consolas", 15, "bold"),
                                anchor="w")
        entry_wrap = tk.Frame(cv, bg=SURF, highlightthickness=1,
                              highlightbackground=EDGE_DIM)
        entry = tk.Entry(entry_wrap, bg=SURF, fg=TEXT, insertbackground=EDGE,
                         relief="flat", font=("Consolas", 11),
                         bd=0, highlightthickness=0,
                         selectbackground=EDGE, selectforeground="#000")
        entry.pack(fill="both", expand=True, padx=8, pady=7)
        entry_win = cv.create_window(44, in_y, window=entry_wrap,
                                     anchor="nw", width=W - 184, height=40)

        def _btn(text, bg, fg, cmd):
            b = tk.Button(cv, text=text, bg=bg, fg=fg, command=cmd,
                          relief="flat", bd=0, highlightthickness=0,
                          font=("Bahnschrift", 9, "bold"), padx=10, pady=4,
                          activebackground=EDGE, activeforeground="#000",
                          cursor="hand2")
            return b

        mic_btn = _btn("\U0001F3A4", TRACK, TEXT, lambda: _mic())
        send_btn = _btn("SEND \u25b8", EDGE, "#04121A", lambda: _submit())
        mic_win = cv.create_window(W - 104, in_y + 20, window=mic_btn,
                                   anchor="center")
        send_win = cv.create_window(W - 46, in_y + 20, window=send_btn,
                                    anchor="center")
        groups["input"] = [prompt, entry_win, mic_win, send_win]
        for wid in (mic_win, send_win):
            interactive.append(wid)

        # ---------- chips row (data-driven from CHIPS)
        chip_ids = []
        cxp, chip_y = 14, _layout(False)["chips"]
        for label, kind, payload in CHIPS:
            wch = int(len(label) * 6.6) + 24
            pill = round_rect(cxp, chip_y, cxp + wch, chip_y + 26, 13,
                              fill=TRACK, outline=EDGE_DIM, width=1)
            txt = cv.create_text(cxp + wch // 2, chip_y + 13, text=label,
                                 fill=TEXT, font=("Bahnschrift", 8))

            def _enter(e, p=pill, t=txt):
                cv.itemconfig(p, fill=EDGE)
                cv.itemconfig(t, fill="#04121A")

            def _leave(e, p=pill, t=txt):
                cv.itemconfig(p, fill=TRACK)
                cv.itemconfig(t, fill=TEXT)

            def _press(e, k=kind, p=payload):
                _chip(k, p)

            for it in (pill, txt):
                cv.tag_bind(it, "<Button-1>", _press)
                cv.tag_bind(it, "<Enter>", _enter)
                cv.tag_bind(it, "<Leave>", _leave)
                interactive.append(it)
            chip_ids += [pill, txt]
            cxp += wch + 8
        groups["chips"] = chip_ids

        # ---------- footer: status · key hints · copy
        status_lbl = tk.Label(cv, text="ready \u00b7 Alt+Space",
                              bg=PANEL, fg=DIM, font=("Bahnschrift", 8))
        status_win = cv.create_window(16, 0, window=status_lbl, anchor="w")
        hints = cv.create_text(
            W // 2, 0,
            text="\u21b5 SEND   ESC CLOSE   \u2191 HISTORY   ALT+SPACE",
            fill=HINT, font=("Bahnschrift", 8))
        copy_id = cv.create_text(W - 20, 0, text="COPY", fill=DIM,
                                 font=("Bahnschrift", 8, "bold"),
                                 anchor="e", state="hidden")
        cv.tag_bind(copy_id, "<Button-1>", lambda e: _copy_last())
        cv.tag_bind(copy_id, "<Enter>",
                    lambda e: cv.itemconfig(copy_id, fill=EDGE))
        cv.tag_bind(copy_id, "<Leave>",
                    lambda e: cv.itemconfig(copy_id, fill=DIM))
        interactive.append(copy_id)
        groups["footer"] = [status_win, hints, copy_id]

        # ---------- mode switch: chrome + widget positions ----------
        def _apply_mode(expanded: bool):
            mode["expanded"] = expanded
            lay = _layout(expanded)
            draw_chrome(expanded)
            for gid in groups.get("reply", []):
                cv.itemconfig(gid, state="normal" if expanded else "hidden")
                if expanded:
                    cv.coords(gid, 14, lay["reply"])
            row = lay["input"]
            cv.coords(prompt, 24, row + 20)
            cv.coords(entry_win, 44, row)
            cv.coords(mic_win, W - 104, row + 20)
            cv.coords(send_win, W - 46, row + 20)
            chip_y2 = lay["chips"]
            xs = 14
            i = 0
            while i < len(chip_ids):
                label, kind, payload = CHIPS[i // 2]
                wch = int(len(label) * 6.6) + 24
                if i % 2 == 0:
                    cv.coords(chip_ids[i], xs, chip_y2,
                              xs + wch, chip_y2 + 26)
                else:
                    cv.coords(chip_ids[i], xs + wch // 2, chip_y2 + 13)
                    xs += wch + 8
                i += 1
            fy = lay["footer"] + 10
            cv.coords(status_win, 16, fy)
            cv.coords(hints, W // 2, fy)
            cv.coords(copy_id, W - 20, fy)
            try:
                x, y = root.winfo_x(), root.winfo_y()
                root.geometry(f"{W}x{lay['h']}+{x}+{y}")
            except Exception:
                pass

        # ---------- state helpers ----------
        def _set_dot(kind: str):
            color = {"busy": BUSY, "danger": DANGER}.get(kind, GOOD)
            try:
                cv.itemconfig(dot_core, fill=color)
            except Exception:
                pass
        _state["dot"] = "good"

        def set_busy(b: bool):
            _state["busy"] = 1 if b else 0
            try:
                if b:
                    _state["dot"] = "busy"
                    status_lbl.configure(text="thinking\u2026", fg=BUSY)
                    send_btn.configure(state="disabled", text="\u2026")
                    cv.itemconfig(copy_id, state="hidden")
                else:
                    _state["dot"] = "good"
                    send_btn.configure(state="normal", text="SEND \u25b8")
            except Exception:
                pass

        def set_status(text, color=DIM):
            try:
                status_lbl.configure(text=text, fg=color)
            except Exception:
                pass

        notice_ticks = {"n": 0}

        def _notice(msg):
            """Background-job ping: flash status + dot (only when up)."""
            try:
                if not _state["visible"]:
                    return
                set_status(("\u23f0 " + str(msg))[:70], GOOD)
                notice_ticks["n"] = 12       # ~1s green flash
            except Exception:
                pass

        def set_reply(text, color=TEXT):
            type_gen["n"] += 1            # cancel any in-flight typing
            try:
                reply.configure(state="normal")
                reply.delete("1.0", "end")
                if text:
                    reply.tag_configure("body", foreground=color)
                    reply.insert("end", text, "body")
                reply.configure(state="disabled")
            except Exception:
                pass

        type_gen = {"n": 0}

        def type_out(text, color=TEXT):
            """Typewriter reveal; a new call cancels the previous one."""
            type_gen["n"] += 1
            gen = type_gen["n"]
            try:
                reply.configure(state="normal")
                reply.delete("1.0", "end")
                reply.tag_configure("body", foreground=color)
                reply.configure(state="disabled")
            except Exception:
                return

            def step(i=0):
                if type_gen["n"] != gen:
                    return                 # superseded by a newer reply
                chunk = text[i:i + 3]
                if not chunk:
                    try:
                        reply.configure(state="disabled")
                        cv.itemconfig(copy_id,
                                      state="normal" if text else "hidden")
                    except Exception:
                        pass
                    return
                try:
                    reply.configure(state="normal")
                    reply.insert("end", chunk, "body")
                    reply.see("end")
                    reply.configure(state="disabled")
                except Exception:
                    return
                root.after(16, lambda: step(i + 3))
            step(0)

        def _copy_last():
            try:
                body = reply.get("1.0", "end").strip()
                if not body:
                    return
                root.clipboard_clear()
                root.clipboard_append(body)
                set_status("copied to clipboard", GOOD)
            except Exception:
                set_status("copy failed", DANGER)

        # ---------- input actions ----------
        def _remember(text):
            hist = _state["history"]
            if not hist or hist[-1] != text:
                hist.append(text)
                del hist[:-100]            # cap history at 100
            _state["hidx"] = len(_state["history"])

        def _submit(prefill=None):
            text = (prefill if prefill is not None
                    else entry.get()).strip()
            if not text:
                return
            if _state.get("busy"):
                return                     # one answer at a time
            try:
                entry.delete(0, "end")
            except Exception:
                pass
            _remember(text)
            if not mode["expanded"]:
                _apply_mode(True)
            set_busy(True)
            set_reply("")
            _state["streaming"] = False    # new round — first delta re-clears
            set_status("thinking\u2026", BUSY)

            def work():
                pieces = []
                try:
                    for piece in _command_stream(text):
                        pieces.append(piece)
                        _actions.put(("delta", piece))
                    full = "".join(pieces).strip()
                    _actions.put(("result", full or "(no reply)"))
                except Exception as exc:
                    _actions.put(("result", f"[error] {exc}"))
            threading.Thread(target=work, daemon=True,
                             name="overlay-cmd").start()

        def _mic():
            if _state.get("busy"):
                return
            set_status("\U0001F399 listening\u2026", BUSY)

            def work():
                try:
                    heard = _listen()
                except Exception as exc:
                    _actions.put(("heard", f"[error] {exc}"))
                    return
                _actions.put(("heard", heard))
            threading.Thread(target=work, daemon=True,
                             name="overlay-mic").start()

        def _chip(kind, payload):
            if kind == "send":
                _submit(payload)
            else:                          # fill: prefill the input
                try:
                    entry.delete(0, "end")
                    entry.insert(0, payload)
                    entry.focus_set()
                    entry.icursor("end")
                except Exception:
                    pass

        # ---------- keys ----------
        def on_key(event):
            if event.keysym in ("Return", "KP_Enter"):
                _submit()
                return "break"
            if event.keysym == "Escape":
                _hide_now()
                return "break"
            if event.keysym in ("Up", "Down"):
                hist = _state["history"]
                if not hist:
                    return "break"
                idx = _state["hidx"]
                if event.keysym == "Up":
                    idx = max(0, idx - 1)
                else:
                    idx = min(len(hist), idx + 1)
                _state["hidx"] = idx
                try:
                    entry.delete(0, "end")
                    if idx < len(hist):
                        entry.insert(0, hist[idx])
                        entry.icursor("end")
                except Exception:
                    pass
                return "break"
            if event.state & 0x2 and event.keysym.lower() == "m":
                _mic()
                return "break"
            return None

        entry.bind("<Key>", on_key)

        def on_focus_out(event=None):
            # Click-away dismisses ONLY an idle, empty deck — never
            # mid-answer. Focus staying inside this process cancels.
            root.after(160, _maybe_focus_hide)

        def _maybe_focus_hide():
            try:
                if not _state["visible"] or _state.get("busy"):
                    return
                if entry.get().strip():
                    return
                if root.focus_displayof() is not None:
                    return          # focus still inside our window
                _hide_now()
            except Exception:
                pass

        root.bind("<FocusOut>", on_focus_out)
        entry.bind("<FocusOut>", on_focus_out)

        # ---------- drag by header ----------
        drag = {"x": 0, "y": 0}

        def drag_start(event):
            drag["x"] = event.x_root - root.winfo_x()
            drag["y"] = event.y_root - root.winfo_y()

        def drag_move(event):
            root.geometry(f"+{event.x_root - drag['x']}"
                          f"+{event.y_root - drag['y']}")

        def on_canvas_click(event):
            if event.y >= 52:
                return                     # header band only
            # ignore clicks that landed on an interactive item
            hits = cv.find_overlapping(event.x - 1, event.y - 1,
                                       event.x + 1, event.y + 1)
            top = hits[-1] if hits else None
            if top is not None and top in interactive:
                return
            drag_start(event)

        def on_canvas_drag(event):
            if drag["x"] or drag["y"]:
                drag_move(event)

        cv.bind("<Button-1>", on_canvas_click)
        cv.bind("<B1-Motion>", on_canvas_drag)
        cv.bind("<ButtonRelease-1>", lambda e: drag.update(x=0, y=0))

        # ---------- show / hide (alpha fade) ----------
        def _fade_in():
            _apply_mode(False)
            try:
                root.deiconify()
                root.lift()
                root.attributes("-topmost", True)
                _state["visible"] = True
                set_status("ready \u00b7 Alt+Space", DIM)
                cv.itemconfig(dot_core, fill=GOOD)
                _state["dot"] = "good"
                x, y = root.winfo_x(), root.winfo_y()
                start_y = y - 14

                def step(a=0.0, i=0):
                    if not _state["visible"]:
                        return
                    a = min(1.0, a + 0.22)
                    root.attributes("-alpha", a)
                    if i < 5:
                        yy = int(start_y + (y - start_y) * (i + 1) / 5)
                        try:
                            root.geometry(f"{W}x{INPUT_H}+{x}+{yy}")
                        except Exception:
                            pass
                    if a < 1.0:
                        root.after(14, lambda: step(a, i + 1))
                    else:
                        try:
                            root.geometry(f"{W}x{INPUT_H}+{x}+{y}")
                            root.focus_force()
                            entry.focus_set()
                            entry.icursor("end")
                        except Exception:
                            pass
                step()
                threading.Thread(target=_pull_info, daemon=True).start()
            except Exception as exc:
                log.warning("overlay fade-in failed: %s", exc)

        def _fade_out():
            try:
                _state["visible"] = False

                def out(a=0.97):
                    try:
                        if _state["visible"]:
                            return         # re-shown mid-fade: abort
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

        def _hide_now():
            _fade_out()

        # ---------- queue pump (never dies) ----------
        def on_delta(piece):
            """Append a live reply piece (first delta clears the well)."""
            try:
                reply.configure(state="normal")
                if not _state.get("streaming"):
                    reply.delete("1.0", "end")
                    reply.tag_configure("body", foreground=TEXT)
                    _state["streaming"] = True
                reply.insert("end", piece, "body")
                reply.see("end")
                reply.configure(state="disabled")
            except Exception:
                pass

        def on_result(text, color=TEXT):
            set_busy(False)
            is_err = text.startswith("[error]")
            if _state.get("streaming"):
                # Live deltas already drew the reply — finalize only.
                _state["streaming"] = False
                try:
                    if is_err and text:
                        reply.tag_configure("err", foreground=DANGER)
                        reply.tag_add("err", "1.0", "end")
                    cv.itemconfig(copy_id,
                                  state="normal" if text else "hidden")
                except Exception:
                    pass
            else:
                type_out(text, color)     # nothing streamed (fast path)
            set_status(("error \u00b7 " if is_err else "done \u00b7 ")
                       + "Alt+Space to recall",
                       DANGER if is_err else DIM)
            _state["dot"] = "danger" if is_err else "good"
            cv.itemconfig(dot_core,
                          fill=DANGER if is_err else GOOD)
            # Mood/model may have changed with this reply — refresh
            # the header right away instead of waiting for the tick.
            threading.Thread(target=_pull_info, daemon=True).start()

        def pump():
            # NEVER dies: one poisoned action must not disable the HUD
            # (the thread stays alive, so ensure_started would keep
            # queueing into a pump that no longer runs — silent no-op).
            try:
                while True:
                    kind, payload = _actions.get_nowait()
                    try:
                        if kind == "delta":
                            on_delta(payload)
                        elif kind == "notice":
                            _notice(payload)
                        elif kind == "result":
                            on_result(payload,
                                      DANGER if payload.startswith("[error]")
                                      else TEXT)
                        elif kind == "heard":
                            if payload.startswith("[error]"):
                                set_status(payload, DANGER)
                            elif payload:
                                _chip("fill", payload)
                                _submit()
                            else:
                                set_status("didn't catch that", DIM)
                        elif kind == "info":
                            try:
                                ver.configure(
                                    text=f"v{payload.get('version','')}")
                                hdr.configure(text=_header_text(payload))
                            except Exception:
                                pass
                        elif kind == "show":
                            _fade_in()
                        elif kind == "hide":
                            _hide_now()
                        elif kind == "toggle":
                            if _state["visible"]:
                                _hide_now()
                            else:
                                _fade_in()
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
                tick["n"] += 1
                if _state["visible"]:
                    if notice_ticks["n"] > 0:
                        # green flash for a finished background job
                        notice_ticks["n"] -= 1
                        on = notice_ticks["n"] % 2 == 0
                        cv.itemconfig(dot_core,
                                      fill=GOOD if on else "#B9FFD9")
                        cv.itemconfig(dot_halo,
                                      outline=GLOW if on else EDGE_DIM)
                    # status-dot pulse while thinking (~320ms cadence)
                    elif _state.get("busy") and tick["n"] % 4 == 0:
                        halo = (BUSY if cv.itemcget(dot_halo,
                                                    "outline") == GLOW
                                else GLOW)
                        cv.itemconfig(dot_halo, outline=halo)
                        cv.itemconfig(dot_core,
                                      fill=(BUSY if halo == GLOW
                                            else "#FFD36B"))
                    elif not _state.get("busy") and \
                            cv.itemcget(dot_halo, "outline") != GLOW:
                        cv.itemconfig(dot_halo, outline=GLOW)
                    if tick["n"] % REFRESH_TICKS == 0:
                        threading.Thread(target=_pull_info,
                                         daemon=True).start()
                root.after(80, pump)
            except Exception:
                pass        # root destroyed — stop rescheduling

        tick = {"n": 0}

        # ---------- wire + go ----------
        _state["root"] = root
        root.report_callback_exception = (
            lambda *a: log.warning("overlay tk callback error: %s", a[1]))
        _apply_mode(False)
        _ready.set()
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


def _hide_now() -> None:
    """Module-level hide used by non-Tk threads (queue-safe)."""
    _actions.put(("hide", ""))


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


def notice(text: str) -> None:
    """Flash the HUD status for a finished background job.

    Only touches an ALREADY-VISIBLE overlay (never forces it on — the
    desktop toast is the reach when the deck is closed).
    """
    if _state["root"] and _state["visible"]:
        _actions.put(("notice", str(text)))
