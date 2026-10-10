"""First-run & boot messaging — the product-facing voice of startup.

Pure helpers: no import-time side effects, no I/O. run.py prints these,
the desktop launcher reuses them for toasts, and tests assert on them
directly. Everything here answers a first-time user's three questions:
which mode am I in, what works, and what do I do next.

The verdicts derive from ONE source — the same /api/health snapshot
the UI banner and the boot log line use — so console, log and UI can
never disagree about the system's state.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# Service name -> what the user loses while it is down (safe-mode wording).
_SERVICE_LOSS = {
    "voice": "speech input/output",
    "browser": "browser automation",
    "mcp": "external MCP tools",
    "scheduler": "scheduled briefings",
    "reminders": "reminders",
    "time_tracker": "time tracking",
    "clipboard": "clipboard watch",
    "screen_context": "screen context",
    "sentinel": "watchdog sentinel",
    "folder_sentinel": "folder watching",
    "app_learner": "app learning",
    "app_close": "close-app skill",
    "webhook_bridge": "webhook bridge",
    "hotkeys": "global hotkeys (Ctrl+Alt+J)",
    "tray": "tray icon",
    "overlay": "HUD overlay (Alt+Space)",
    "flask": "web UI",
}


def _short(exc: BaseException, limit: int = 60) -> str:
    s = str(exc) or exc.__class__.__name__
    return s[:limit]


def status_lines(s, skills_only: bool = False) -> List[str]:
    """The boot status block (console).

    Every subsystem read here is guarded: a broken memory DB or an
    unreadable mood must degrade to an "unavailable" line — never a
    crashed boot. This is the first thing a new user sees, so each
    line is either a fact or an instruction.
    """
    from config import VERSION
    lines = [f"  JARVIS v{VERSION} starting...",
             f"  URL     : http://{s.host}:{s.port}"]
    if skills_only:
        lines += [
            "  [*] SKILLS-ONLY mode — no API key set",
            "      Works now : local skills, memory, reminders, health, HUD",
            "      Not yet   : LLM chat / AI answers",
            "      Fix it    : Settings -> GENERAL -> paste "
            "DEEPSEEK_API_KEY -> SAVE+TEST",
            "                  (or: notepad .env), then restart",
        ]
    else:
        lines.append(f"  Model   : {s.model}")
    voice = (getattr(s, "voice_name", "") or "").strip()
    lines.append(f"  Voice   : {voice + '  (British)' if voice else 'disabled (VOICE_NAME empty)'}")
    try:
        import moods
        lines.append(f"  Mood    : {moods.current_name()}")
    except Exception as exc:
        lines.append(f"  Mood    : unavailable ({_short(exc)}) — default in use")
    try:
        import memory
        lines.append(f"  Memory  : {len(memory.all_facts())} facts on file")
    except Exception as exc:
        lines.append(f"  Memory  : UNAVAILABLE ({_short(exc)}) — running "
                     "without persistent memory")
    lines.append("  Mode    : " +
                 ("DEV (debug on)" if getattr(s, "debug", False)
                  else "production"))
    lines.append("  Logs    : logs/jarvis.log")
    return lines


def safe_mode_block(failed, healthy: Optional[int] = None,
                    skills_only: bool = False) -> List[str]:
    """The honest degraded-boot block: what failed, what works, next step.

    Returns [] when nothing failed — callers print nothing on a clean
    boot.
    """
    failed = [f for f in (failed or []) if f]
    if not failed:
        return []
    loss = [_SERVICE_LOSS.get(f, f.replace("_", " ")) for f in failed]
    total = (healthy + len(failed)) if healthy is not None else None
    if total:
        head = (f"  [~~] SAFE MODE — {len(failed)} of {total} services "
                f"failed ({', '.join(failed)})")
    else:
        head = (f"  [~~] SAFE MODE — {len(failed)} service(s) failed "
                f"({', '.join(failed)})")
    works = ["web UI", "API", "local skills", "memory"]
    if not skills_only:
        works.append("LLM chat")
    if healthy:
        works.append(f"{healthy} of {total} services")
    return ["",
            head,
            f"      What's broken : {'; '.join(loss)}",
            f"      What works    : {', '.join(works)}",
            "      What to do    : open Settings -> SYSTEM and RESTART "
            "the failed service, or see logs/jarvis.log"]


def health_block(snapshot: Dict[str, Any]) -> List[str]:
    """Startup health verdict from the /api/health snapshot.

    ok      -> one reassurance line
    warn    -> the config-warning count + where to look
    degraded-> the safe-mode block (service failures name the loss,
               probe-level degradation names the check + detail)
    skills-only is derived from the api_key check, never assumed.
    """
    snap = snapshot or {}
    overall = snap.get("overall") or "unknown"
    checks = snap.get("checks") or {}
    skills_only = (checks.get("api_key") or {}).get("status") != "ok"
    items = (checks.get("services") or {}).get("items") or {}
    failed = [k for k, v in items.items()
              if isinstance(v, dict) and not v.get("ok")]
    if failed:
        return safe_mode_block(failed, len(items) - len(failed), skills_only)
    if overall == "degraded":
        bad = [k for k, c in checks.items()
               if isinstance(c, dict) and c.get("status") == "degraded"]
        lines = ["", "  [~~] SAFE MODE — degraded" +
                 (f": {', '.join(bad)}" if bad else "")]
        if bad:
            detail = str((checks.get(bad[0]) or {}).get("detail") or "")
            lines.append(f"      Detail      : {detail[:120]}")
        lines.append("      What to do  : GET /api/health, or open "
                     "Settings -> SYSTEM")
        return lines
    if overall == "warn":
        cw = (checks.get("config") or {}).get("warnings") or []
        tail = f" — {cw[0]}" if cw else ""
        return ["",
                f"  Health : WARN — {len(cw)} config warning(s){tail}",
                "          Where  : GET /api/health, or Settings -> SYSTEM"]
    if overall == "ok":
        pending = sorted(k for k, v in items.items()
                         if isinstance(v, dict) and v.get("detail") == "starting")
        if pending:
            # Async services (MCP, voice warmup) may still be settling —
            # never claim "all healthy" while something is in flight.
            return ["",
                    f"  Health : OK so far — still starting: "
                    f"{', '.join(pending)}",
                    "          Final verdict: GET /api/health in ~1 min"]
        return ["", "  Health : OK — all systems healthy"]
    return ["", f"  Health : {overall}"]


def toast_status(failed=None, has_key: bool = True) -> str:
    """Immediate boot-toast text (desktop mode)."""
    failed = [f for f in (failed or []) if f]
    if failed:
        return (f"Safe mode: {', '.join(failed[:3])} failed — press "
                "Ctrl+Alt+J, then Settings > SYSTEM")
    if not has_key:
        return "Skills-only mode (no API key) — press Ctrl+Alt+J to open"
    return "Press Ctrl+Alt+J to open"


def degraded_toast(snapshot: Dict[str, Any]) -> Optional[str]:
    """Deferred (T+20s) toast text when services failed async, else None.

    Returns the message only — callers decide whether to toast, so
    tests can assert without popping windows.
    """
    snap = snapshot or {}
    items = ((snap.get("checks") or {}).get("services") or {}).get("items") or {}
    failed = [k for k, v in items.items()
              if isinstance(v, dict) and not v.get("ok")]
    if not failed:
        return None
    return (f"{len(failed)} service(s) failed: {', '.join(failed[:3])} — "
            "open Settings > SYSTEM to restart")


def toast_if_degraded(snapshot: Dict[str, Any]) -> None:
    """Deferred health toast (desktop mode); silent when healthy."""
    msg = degraded_toast(snapshot)
    if not msg:
        return
    try:
        from system import notify
        notify.toast("JARVIS is in safe mode", msg)
    except Exception:
        pass


def bind_error(exc: BaseException, host: str, port: Any) -> str:
    """Friendly text for a failed listen() — no tracebacks for users."""
    return (f"\n  [!!] Could not start the server on {host}:{port} — "
            f"{exc}\n"
            "      Another program (or an old JARVIS) is using that port.\n"
            "      Fix: stop the other copy (check logs/jarvis.lock), or\n"
            "      set a free PORT in .env and start again.\n")


def ensure_port(host: Any, port: Any) -> Optional[str]:
    """Probe-bind the port before booting subsystems.

    Returns None when the port looks free, otherwise the OS error text.
    Why: werkzeug swallows its own bind failures and sys.exit(1)s with a
    terse message AFTER everything booted — checking first turns the
    single most common startup failure into an instant, friendly answer.
    """
    import socket
    try:
        p = int(port)
    except (TypeError, ValueError):
        return None          # garbage port: config audit handles it
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # EXCLUSIVEADDRUSE: with plain sockets Windows can report the
        # port "free" to a second binder — be strict here on purpose.
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET,
                            socket.SO_EXCLUSIVEADDRUSE, 1)
        sock.bind((str(host or "127.0.0.1"), p))
        return None
    except OSError as exc:
        if isinstance(exc, (socket.gaierror,)):
            return None      # unresolvable host: not a "busy port"
        return str(exc) or exc.__class__.__name__
    except Exception:
        return None          # never block boot on the probe itself
    finally:
        try:
            sock.close()
        except Exception:
            pass
