"""OpenCode CLI bridge — auto-start headless server + run tasks."""

from __future__ import annotations
import os
import shutil
import subprocess
import time
from typing import Optional
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

PORT = int(os.getenv("OPENCODE_PORT", "4096"))
URL = f"http://127.0.0.1:{PORT}"
HOST = "127.0.0.1"

_proc: Optional[subprocess.Popen] = None


def _opencode_exe() -> str | None:
    """Find the opencode executable on PATH (Windows-safe)."""
    for name in ("opencode.cmd", "opencode.exe", "opencode"):
        p = shutil.which(name)
        if p:
            return p
    return None


def _hidden_popen_kwargs() -> dict:
    kw = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kw["creationflags"] = (
            subprocess.CREATE_NO_WINDOW
            | subprocess.DETACHED_PROCESS
        )
    return kw


def start_server() -> bool:
    """Start opencode serve --port 4096 in the background."""
    global _proc

    if _proc and _proc.poll() is None:
        return True   # already running

    exe = _opencode_exe()
    if not exe:
        log.error("opencode not found on PATH. Install: npm i -g opencode-ai")
        return False

    try:
        cmd = [exe, "serve", "--port", str(PORT), "--hostname", HOST]
        _proc = subprocess.Popen(cmd, **_hidden_popen_kwargs())
        log.info("OpenCode server started (pid=%s, port=%d)",
                 _proc.pid, PORT)

        # Give it a moment to bind
        time.sleep(2)
        return _proc.poll() is None
    except Exception as exc:
        log.exception("Failed to start opencode serve: %s", exc)
        return False


def stop_server() -> bool:
    global _proc
    if _proc is None:
        return False
    try:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _proc.kill()
        log.info("OpenCode server stopped")
        _proc = None
        return True
    except Exception as exc:
        log.warning("Stop failed: %s", exc)
        _proc = None
        return False


WEB_TITLE = "OpenCode Web"


def web_url() -> str:
    """Public URL of the OpenCode web interface."""
    return URL + "/"


def is_web_up(timeout: int = 3) -> bool:
    """True if something answers HTTP on the OpenCode port.

    Any HTTP response counts — even 401 (auth-gated still means
    the server is up and the browser tab will load).
    """
    import urllib.request
    import urllib.error
    try:
        urllib.request.urlopen(URL, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True
    except Exception:
        return False


def launch_web_terminal() -> dict:
    """Open a visible terminal running `opencode web` for the web UI.

    Returns {"ok": True, "url": ..., "already": ...}.
    Never starts a duplicate server: if the port already answers,
    just returns the URL so the caller can open the tab.
    """
    exe = _opencode_exe()
    if not exe:
        return {"ok": False,
                "error": "opencode not installed. Run: npm i -g opencode-ai"}

    if is_web_up():
        return {"ok": True, "url": web_url(), "already": True}

    # Free the port if our own hidden server holds it.
    if _proc is not None and _proc.poll() is None:
        stop_server()
        time.sleep(1)

    inner = f'"{exe}" web --port {PORT} --hostname {HOST}'
    # Best-effort: stop `opencode web` from opening its own browser tab.
    # The frontend opens exactly one tab once the server is up.
    env = dict(os.environ, BROWSER="none")
    try:
        wt = shutil.which("wt.exe") or shutil.which("wt")
        if wt:
            subprocess.Popen(
                [wt, "new-tab", "--title", WEB_TITLE,
                 "cmd", "/k", inner],
                env=env)
        else:
            subprocess.Popen(
                f'start "{WEB_TITLE}" cmd /k "{inner}"',
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
                ),
            )
        log.info("Launched OpenCode web terminal")
        return {"ok": True, "url": web_url(), "already": False}
    except Exception as exc:
        log.exception("Failed to launch OpenCode terminal")
        return {"ok": False, "error": str(exc)[:200]}


def run_task(task: str, timeout: int = 300) -> str:
    """Run a task through opencode run (attaching to the local server)."""
    exe = _opencode_exe()
    if not exe:
        return "opencode not installed. Run: npm i -g opencode-ai"

    # Ensure server is up (fallback: opencode run will start its own)
    if not (_proc and _proc.poll() is None):
        log.info("Server not running -- opencode run will spawn its own")

    # Load active model from prefs
    from skills.opencode_models import get_active_model
    active_model = get_active_model()

    cmd = [
        exe, "run", task,
        "--attach", URL,
        "--print-logs",
    ]
    if active_model:
        cmd += ["--model", active_model]

    try:
        log.info("OpenCode task: %r", task[:100])
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            creationflags=(
                subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            ),
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()

        if result.returncode != 0 and not out:
            return f"OpenCode failed: {err[:400] or 'unknown error'}"

        # OpenCode prints logs to stderr -- take only stdout as reply
        if not out:
            out = err

        # Trim to something speakable
        if len(out) > 3000:
            out = out[:3000] + "\n...(truncated)"

        return out or "OpenCode returned no output."
    except subprocess.TimeoutExpired:
        return f"OpenCode timed out after {timeout}s."
    except Exception as exc:
        log.exception("opencode run failed")
        return f"OpenCode error: {str(exc)[:200]}"


def is_running() -> bool:
    return bool(_proc and _proc.poll() is None)


# ---------- Skills ----------

@register("opencode_task", [
    r"^(?:open\s*code|opencode)[,:\s]+(?P<task>.+?)[\?\.\!]?$",
    r"^(?:ask\s+open\s*code\s+to|tell\s+open\s*code\s+to)\s+(?P<task2>.+?)[\?\.\!]?$",
], "Send a task to OpenCode")
def s_task(text, m):
    gd = m.groupdict()
    task = (gd.get("task") or gd.get("task2") or "").strip()
    if not task or len(task) < 3:
        return None
    if not is_running():
        start_server()
    return run_task(task)


@register("opencode_status", [
    r"^open\s*code\s+status[\?\.\!]?$",
], "OpenCode server status")
def s_status(text, m):
    if is_running():
        return f"OpenCode server is running at {URL}."
    return "OpenCode server is not running."


@register("opencode_start", [
    r"^start\s+open\s*code[\?\.\!]?$",
], "Start OpenCode")
def s_start(text, m):
    return "OpenCode started." if start_server() else "Failed to start OpenCode."


@register("opencode_stop", [
    r"^stop\s+open\s*code[\?\.\!]?$",
], "Stop OpenCode")
def s_stop(text, m):
    stop_server()
    return "OpenCode stopped."
