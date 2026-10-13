"""OS Mode — autonomous driver on JARVIS's own engine.

Mission -> propose -> confirm (voice/toast) -> execute -> self-correct.
Tiers come from the unified table (ai.permissions): AUTO tools run
free, everything else asks first; unknown tools are refused. The one
mission-context rule: mcp__ tools run free inside supervised missions
(autonomy_enabled kill switch covers all of them). Kill switch:
autonomy_enabled=false.
"""
from __future__ import annotations
import json
import threading
import time
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)
_MAX_ROUNDS = 10
_NAG_GAP = 300  # min seconds between unprompted speeches

try:
    from ai import permissions as _permissions
    AUTO_TOOLS = set(_permissions.auto_tools())
except Exception:
    AUTO_TOOLS = {
        "remember_fact", "read_own_code", "deep_search",
        "silent_browse", "silent_search", "silent_read",
        "fs_read", "fs_list", "fs_search", "list_open_apps",
        "read_screen", "folder_watch", "folder_unwatch", "open_url",
        "outcome_stats", "reality_check_tool", "switch_mood",
        "silent_click",
    }

# Never offered to missions: nested-agent recursion (missions already ARE
# an agent; computer_run would spawn an agent inside the agent).
MISSION_EXCLUDED = {"computer_run"}

_last_spoke = 0.0
_lock = threading.Lock()


def _audit(action: str, target: str, ok: bool, extra: str = "") -> None:
    # Single shared trail (system/audit.py): OS-mission steps sit in
    # the same file as chat-loop tool calls and consent verdicts.
    try:
        from system import audit as _audit_trail
        _audit_trail.record(action, target, ok=ok, extra=extra)
    except Exception:
        pass


def enabled() -> bool:
    try:
        from memory import get_pref
        return bool(get_pref("autonomy_enabled", False))
    except Exception:
        return False


def _may_speak() -> bool:
    try:
        from memory import get_pref
        if get_pref("dnd", False):
            return False
        from voice import is_speaking
        if is_speaking():
            return False
    except Exception:
        pass
    with _lock:
        if time.time() - _last_spoke < _NAG_GAP:
            return False
    return True


def _mark_spoke() -> None:
    global _last_spoke
    with _lock:
        _last_spoke = time.time()


def say(text: str, force: bool = False) -> str:
    """Dynamic voice: speak unless DND/busy/recent; else toast + log."""
    if not text:
        return "silent"
    if not force and not _may_speak():
        try:
            from system.notify import notify
            notify("JARVIS", text)
        except Exception:
            pass
        log.info("Say (muted): %r", text[:150])
        return "toast"
    try:
        from voice import speak_async
        speak_async(text)
        _mark_spoke()
        return "spoken"
    except Exception as exc:
        log.warning("Say failed: %s", exc)
        return "failed"


def ask_approval(question: str) -> bool:
    """Dynamic confirm: voice when present, toast buttons otherwise."""
    try:
        from memory import get_pref
        timeout = int(get_pref("autonomy_confirm_timeout", 120))
    except Exception:
        timeout = 120
    # Voice path (skipped under DND or without mic/STT).
    try:
        from memory import get_pref
        if not get_pref("dnd", False):
            from voice import speak_async, is_speaking
            if not is_speaking():
                speak_async(question + " Say yes or no.")
                _mark_spoke()
                from voice import listen_until_silence
                heard = listen_until_silence(verbose=False) or ""
                low = heard.lower()
                log.info("Approval heard: %r", heard[:80])
                if any(w in low for w in ("yes", "yeah", "yep", "ok",
                                          "approve", "do it", "نعم", "اي")):
                    return True
                if any(w in low for w in ("no", "nope", "don't", "stop",
                                          "cancel", "لا")):
                    return False
    except Exception as exc:
        log.debug("Voice approval unavailable: %s", exc)
    # Toast path (also the fallback). Default NO.
    try:
        from system.notify import confirm
        return bool(confirm(question, timeout=timeout))
    except Exception:
        return False


def gated_execute(name: str, args: dict, dry_run: bool = False) -> str:
    from ai.tools import execute_tool
    if name not in AUTO_TOOLS and not name.startswith("mcp__"):
        # Confirm tier (unknown names land here too).
        if dry_run:
            _audit("propose", f"{name} {str(args)[:80]}", True, "dry-run")
            return f"[dry-run] would ask approval for {name}"
        ok = ask_approval(f"Allow {name}? {str(args)[:120]}")
        if not ok:
            _audit(name, str(args)[:80], False, "denied")
            return f"Denied by user: {name} was not executed."
    else:
        if dry_run and name not in AUTO_TOOLS:
            return f"[dry-run] would ask approval for {name}"
    if dry_run and name not in AUTO_TOOLS:
        return f"[dry-run] skipped {name}"
    try:
        if dry_run:
            _audit("propose", f"{name} {str(args)[:80]}", True, "dry-run")
            return f"[dry-run] {name} not executed"
        # The run itself is audit-trailed inside execute_tool
        # (single choke point); proposals and denials stay here.
        return execute_tool(name, args or {})
    except Exception as exc:
        return f"Tool error: {exc}"


def _snapshot() -> str:
    lines = [f"cwd: {Path.cwd()}", f"OS: Windows"]
    try:
        from memory import get_pref
        allowed = get_pref("code_mode_allowed", []) or []
        if allowed:
            lines.append("allowed paths: " + ", ".join(map(str, allowed)))
        lines.append("code_mode: " + str(bool(
            get_pref("code_mode_enabled", False))))
    except Exception:
        pass
    try:
        from memory import context as ctx
        for e in ctx.recent_events(minutes=60, limit=8):
            lines.append(f"recent {e.get('kind')}: {e.get('detail', '')[:100]}")
    except Exception:
        pass
    return "\n".join(lines)


def run_mission(goal: str, dry_run: bool = False,
                max_rounds: int = _MAX_ROUNDS) -> dict:
    """Bounded ReAct loop over existing tools. Returns summary dict."""
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "error": "Empty goal."}
    from ai.client import get_client
    from ai.tools import TOOL_SCHEMAS, mcp_schemas
    from moods.router import FAST_MODEL
    schemas = [t for t in TOOL_SCHEMAS
               if t.get("function", {}).get("name") not in MISSION_EXCLUDED]
    schemas += mcp_schemas()
    messages = [
        {"role": "system",
         "content": ("You are JARVIS, autonomous OS agent. Complete the "
                     "mission with tools. Be terse. Environment:\n"
                     + _snapshot())},
        {"role": "user", "content": goal},
    ]
    c = get_client()
    final = ""
    try:
        for rnd in range(max(1, max_rounds)):
            resp = c._client.chat.completions.create(
                model=FAST_MODEL, messages=messages,
                tools=schemas or None, temperature=0.2, max_tokens=800)
            msg = resp.choices[0].message
            text = (msg.content or "").strip()
            if text:
                final = text
            tcs = getattr(msg, "tool_calls", None)
            if not tcs:
                break
            messages.append({"role": "assistant", "content": text,
                             "tool_calls": [
                                 {"id": t.id, "type": "function",
                                  "function": {"name": t.function.name,
                                               "arguments": t.function.arguments}}
                                 for t in tcs]})
            for t in tcs:
                try:
                    args = json.loads(t.function.arguments or "{}")
                except Exception:
                    args = {}
                out = gated_execute(t.function.name, args, dry_run=dry_run)
                messages.append({"role": "tool", "tool_call_id": t.id,
                                 "content": str(out)[:2000]})
        _audit("mission", goal[:80], True,
               f"rounds<={max_rounds} dry={dry_run}")
        return {"ok": True, "result": final, "dry_run": dry_run}
    except Exception as exc:
        log.warning("Mission failed: %s", exc)
        _audit("mission", goal[:80], False, str(exc)[:80])
        return {"ok": False, "error": str(exc)[:300]}


def tick(dry_run: bool = False) -> dict:
    """Background tick: investigate only when something looks off."""
    if not enabled() and not dry_run:
        return {"ok": True, "idle": True}
    interesting = []
    try:
        from memory import context as ctx
        errs = ctx.recent_errors(hours=1, limit=5)
        for e in errs:
            interesting.append(f"error: {str(e)[:150]}")
    except Exception:
        pass
    if not interesting:
        log.debug("Agent tick: quiet")
        return {"ok": True, "idle": True}
    res = run_mission("Investigate and report, do not break anything:\n"
                      + "\n".join(interesting[:5]), dry_run=dry_run)
    if res.get("ok") and res.get("result"):
        say(res["result"][:300])
    return res
