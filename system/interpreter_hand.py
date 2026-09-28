"""Open Interpreter as JARVIS's execution hand (subordinate tool).

JARVIS stays the brain (DeepSeek), voice, memory, and HUD. This module
owns one configured Interpreter instance pointed at the same provider
(TokenHarbor via LiteLLM's OpenAI-compatible path) and runs goals in a
worker thread — it blocks, so Flask never waits on it.

Safety rules (non-negotiable):
- auto_run stays False: code the model writes is proposed, never fired blindly.
- Package-level approval is JARVIS's dynamic rule (voice/toast), enforced
  by the CALLER (agent loop / OS Mode), not here.
- Every execution is appended to logs/code_mode_audit.log.
- Fresh conversation per task (no cross-task contamination).
- All imports lazy: without the package installed every entry point
  returns a clear install hint instead of crashing the boot.
"""
from __future__ import annotations
import threading
import time
from datetime import datetime
from pathlib import Path
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_AUDIT = _ROOT / "logs" / "code_mode_audit.log"

_lock = threading.Lock()
_interp = None


def is_available() -> bool:
    try:
        __import__("interpreter")
        return True
    except ImportError:
        return False


def status() -> dict:
    if not is_available():
        return {"ok": False,
                "error": "open-interpreter not installed. "
                         "Run: pip install open-interpreter==0.4.3"}
    try:
        cfg = _describe()
        return {"ok": True, **cfg}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def _audit(action: str, target: str, ok: bool, extra: str = "") -> None:
    try:
        ts = datetime.now().isoformat(timespec="seconds")
        status = "OK" if ok else "FAIL"
        with open(_AUDIT, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {status:4} {action:12} {target} {extra}\n")
    except Exception:
        pass


def _describe() -> dict:
    from config import get_settings
    from moods.router import FAST_MODEL
    s = get_settings()
    model_id = FAST_MODEL
    return {
        "api_base": s.base_url,
        "model": f"openai/{model_id}",
        "auto_run": False,
        "offline": False,
        "os_mode": False,
    }


def _get():
    """Configured singleton. Raises RuntimeError with a plain message."""
    global _interp
    with _lock:
        if _interp is not None:
            return _interp
        try:
            from interpreter import interpreter as it
        except ImportError:
            raise RuntimeError(
                "open-interpreter not installed. "
                "Run: pip install open-interpreter==0.4.3")
        from config import get_settings
        from moods.router import FAST_MODEL
        s = get_settings()
        it.llm.api_base = s.base_url
        it.llm.api_key = s.api_key
        it.llm.model = f"openai/{FAST_MODEL}"  # prefix REQUIRED for routing
        it.llm.context_window = 32000  # declared: LiteLLM can't infer it
        it.llm.max_tokens = 2000
        it.llm.temperature = 0.2
        it.auto_run = False
        it.offline = False
        it.os = False  # no vision model on this provider yet
        it.verbose = False
        _interp = it
        log.info("Interpreter hand ready (model=openai/%s)", FAST_MODEL)
        return _interp


def reset_conversation() -> None:
    try:
        it = _get()
        it.messages = []
    except Exception:
        pass


def run_goal(goal: str, timeout: int = 300) -> dict:
    """Run one goal synchronously. Returns {ok, output, error}.

    With auto_run=False the model may propose code and stop for approval;
    the CALLER drives approval. This function returns whatever the turn
    produced (proposals included) without executing unapproved code itself.
    """
    goal = (goal or "").strip()
    if not goal:
        return {"ok": False, "error": "Empty goal."}
    t0 = time.time()
    try:
        it = _get()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}
    try:
        with _lock:
            it.messages = []
            chunks = []
            for chunk in it.chat(goal, stream=False, display=False):
                if isinstance(chunk, dict):
                    if chunk.get("role") == "assistant":
                        c = chunk.get("content")
                        if c:
                            chunks.append(str(c))
                    if chunk.get("type") == "confirmation":
                        break  # approval belongs to the caller, not us
            output = "\n".join(chunks).strip()
        el = time.time() - t0
        _audit("oi-goal", goal[:80], True, f"{el:.1f}s")
        log.info("Interpreter goal done in %.1fs", el)
        return {"ok": True, "output": output, "seconds": round(el, 1)}
    except Exception as exc:
        _audit("oi-goal", goal[:80], False, str(exc)[:80])
        log.warning("Interpreter goal failed: %s", exc)
        return {"ok": False, "error": str(exc)[:300]}


def run_goal_async(goal: str, on_done=None) -> threading.Thread:
    """Non-blocking wrapper. on_done(result_dict) runs in worker thread."""
    def _work():
        res = run_goal(goal)
        if on_done:
            try:
                on_done(res)
            except Exception as exc:
                log.warning("Interpreter callback failed: %s", exc)
    t = threading.Thread(target=_work, name="interpreter-hand", daemon=True)
    t.start()
    return t
