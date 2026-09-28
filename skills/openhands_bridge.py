"""OpenHands bridge via SDK runner subprocess."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_ROOT = Path(__file__).resolve().parent.parent
_RUNNER = _ROOT / "scripts" / "openhands_runner.py"
_OH_PY = Path(r"C:\openhands-env\.venv\Scripts\python.exe")
_TIMEOUT = int(os.getenv("OPENHANDS_TIMEOUT", "300"))


def _available() -> bool:
    if not _OH_PY.exists() or not _RUNNER.exists():
        return False
    try:
        import urllib.request
        host = os.getenv("OPENHANDS_HOST", "127.0.0.1")
        port = os.getenv("OPENHANDS_PORT", "8000")
        req = urllib.request.Request(f"http://{host}:{port}/health")
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def _env_for_runner() -> dict:
    env = dict(os.environ)

    def _env_val(key: str, default: str = "") -> str:
        try:
            with open(_ROOT / ".env", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith(key + "="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return default

    env["DEEPSEEK_API_KEY"] = _env_val("DEEPSEEK_API_KEY")
    env["DEEPSEEK_BASE_URL"] = _env_val("DEEPSEEK_BASE_URL", "https://tokenharbor.ai/v1")
    env["OPENHANDS_HOST"] = os.getenv("OPENHANDS_HOST", "127.0.0.1")
    env["OPENHANDS_PORT"] = os.getenv("OPENHANDS_PORT", "8000")
    env["OPENHANDS_SESSION_KEY"] = os.getenv("OPENHANDS_SESSION_KEY", "").strip()
    env["OPENHANDS_WORKING_DIR"] = str(_ROOT)
    env["OPENHANDS_MODEL"] = os.getenv("OPENHANDS_MODEL", "openai/deepseek-v4.1-flash:free")
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_task(task: str, timeout: int | None = None) -> str:
    if not _OH_PY.exists():
        return f"Python 3.12 env not found at {_OH_PY}."
    if not _RUNNER.exists():
        return f"Runner not found at {_RUNNER}."
    if not _available():
        return "OpenHands server not running."
    try:
        result = subprocess.run(
            [str(_OH_PY), str(_RUNNER), task],
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=timeout or _TIMEOUT,
            env=_env_for_runner(), cwd=str(_RUNNER.parent))
    except subprocess.TimeoutExpired:
        return "OpenHands task timed out."
    except Exception as exc:
        log.exception("Runner spawn failed")
        return f"Runner error: {str(exc)[:150]}"

    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if result.returncode == 0 and out:
        lines = out.splitlines()
        capture = False
        agent_lines: list[str] = []
        for line in lines:
            if line.startswith("Message from Agent"):
                capture = True
                continue
            if capture and line.startswith("Tokens:"):
                capture = False
                continue
            if capture and line.strip():
                agent_lines.append(line.strip())
        if agent_lines:
            return agent_lines[-1]
        return out[-500:] if len(out) > 500 else out
    if err:
        return f"OpenHands failed: {err[:300]}"
    return "OpenHands returned no output."


@register("openhands_task", [
    r"^(?:use\s+openhands\s+to|let\s+openhands|delegate\s+to\s+openhands)\s+(?P<task>.+?)[\?\.\!]?$",
], "Delegate a task to OpenHands")
def s_task(text, m):
    task = (m.group("task") or "").strip()
    if not task or len(task) < 5:
        return None
    return run_task(task)


@register("openhands_browse", [
    r"^(?:use\s+openhands\s+to\s+)?browse\s+(?P<url>https?://\S+)(?:\s+and\s+(?P<what>.+?))?[\?\.\!]?$",
], "Browse via OpenHands")
def s_browse(text, m):
    url = m.group("url").strip()
    what = (m.group("what") or "tell me what you see").strip()
    if not url:
        return None
    return run_task(f"Open {url} and {what}")


@register("openhands_code", [
    r"^(?:use\s+openhands\s+to\s+)?(?:write|create|build)\s+(?:a\s+)?(?:python\s+)?script\s+(?:that\s+)?(?P<what>.+?)[\?\.\!]?$",
], "Write code via OpenHands")
def s_code(text, m):
    what = (m.group("what") or "").strip()
    if not what:
        return None
    return run_task(f"Write a Python script that {what}. Save to scripts/ and test it.")


@register("openhands_status", [
    r"^openhands\s+status[\?\.\!]?$",
], "OpenHands status")
def s_status(text, m):
    if not _OH_PY.exists():
        return f"Python env missing: {_OH_PY}"
    if not _RUNNER.exists():
        return f"Runner missing: {_RUNNER}"
    if _available():
        return "OpenHands SDK bridge ready (server running)."
    return "OpenHands server is not running."
