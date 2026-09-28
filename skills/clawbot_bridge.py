"""ClawBot Plus bridge — full computer control for JARVIS."""
from __future__ import annotations
import os
import shutil
import subprocess
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_CLAWBOT_TIMEOUT = 180


def _clawbot_installed() -> bool:
    return shutil.which("clawbot") is not None


def _run_clawbot(task: str, timeout: int = _CLAWBOT_TIMEOUT) -> str | None:
    if not _clawbot_installed():
        return None
    try:
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        env["DEEPSEEK_API_KEY"] = os.getenv("DEEPSEEK_API_KEY", "")
        result = subprocess.run(
            ["clawbot", "--task", task],
            capture_output=True, text=True, timeout=timeout, env=env)
        if result.returncode != 0:
            log.warning("ClawBot failed: %s", result.stderr[:200])
            return None
        return result.stdout.strip() or None
    except subprocess.TimeoutExpired:
        return f"ClawBot task timed out after {timeout}s."
    except Exception as exc:
        log.exception("ClawBot bridge error: %s", exc)
        return None


@register("clawbot_control", [
    r"^(?:use\s+clawbot\s+to|let\s+clawbot)\s+(?P<task>.+?)[\?\.\!]?$",
], "ClawBot Plus autonomous control")
def s_clawbot(text, m):
    task = (m.group("task") or "").strip()
    if not task or len(task) < 5:
        return None
    result = _run_clawbot(task)
    if result:
        return result
    return "ClawBot Plus not available yet. Requires Python 3.11+."


@register("clawbot_browse", [
    r"^(?:use\s+clawbot\s+to\s+)?browse\s+(?P<url>https?://\S+)[\?\.\!]?$",
], "Browse a URL via ClawBot")
def s_browse(text, m):
    url = m.group("url").strip()
    if not url:
        return None
    return _run_clawbot(f"Open {url} and describe what you see")


@register("clawbot_click", [
    r"^clawbot\s+click\s+(?P<target>.+?)[\?\.\!]?$",
], "Click via ClawBot")
def s_click(text, m):
    target = (m.group("target") or "").strip()
    if not target:
        return None
    return _run_clawbot(f"Click on {target}")


@register("clawbot_type", [
    r"^clawbot\s+type\s+(?P<text>.+?)[\?\.\!]?$",
], "Type via ClawBot")
def s_type(text, m):
    txt = (m.group("text") or "").strip()
    if not txt:
        return None
    return _run_clawbot(f"Type this text: {txt}")


@register("clawbot_status", [
    r"^clawbot\s+status[\?\.\!]?$",
], "ClawBot status")
def s_status(text, m):
    if _clawbot_installed():
        return "ClawBot Plus is installed and ready."
    return "ClawBot Plus not installed yet."
