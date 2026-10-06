"""Self-update: check GitHub for a newer JARVIS and pull it.

git-based (the install is a clone of the GitHub repo), so the same
checkout that lets you push your work lets JARVIS fetch ours:

  check()   fetch origin/main, compare HEAD, report the remote VERSION.
  update()  fast-forward pull — refuses to run over local changes or
            local commits so nothing you did is ever overwritten.

Untracked personal files (.env, jarvis_config.json, ...) never block a
pull; only edits to tracked files do. After a pull the running process
still has the old code loaded — restart JARVIS to finish.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from logger import get_logger

log = get_logger("updater")

ROOT = Path(__file__).resolve().parents[1]
_GIT_TIMEOUT = 45  # network fetches can be slow on bad connections


def _run_git(args: List[str], timeout: int = _GIT_TIMEOUT) -> subprocess.CompletedProcess:
    """Run git in the repo root. Never raises for git failures."""
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), *args],
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 127, "", "git not found")
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "git timed out")
    except Exception as exc:  # pragma: no cover - defensive
        return subprocess.CompletedProcess(args, 1, "", str(exc))


def _parse_version(text: str) -> Optional[str]:
    """Pull VERSION = "x.y.z" out of a config.py source blob."""
    m = re.search(r'^\s*VERSION\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return m.group(1) if m else None


def _local_version() -> str:
    try:
        from config import VERSION
        return VERSION
    except Exception:
        return "0.0.0"


def _dirty_files(limit: int = 10) -> List[str]:
    """Tracked files with local edits (untracked personal files don't count)."""
    r = _run_git(["status", "--porcelain", "--untracked-files=no"])
    if r.returncode != 0:
        return []
    out = []
    for line in (r.stdout or "").splitlines():
        if line.strip():
            out.append(line[3:].strip())
    return out[:limit]


def check() -> Dict[str, Any]:
    """Fetch origin/main and report whether a newer version exists.

    Returns {ok, current, latest, available, dirty, reason}.
    """
    result: Dict[str, Any] = {
        "ok": False,
        "current": _local_version(),
        "latest": _local_version(),
        "available": False,
        "dirty": False,
        "reason": "",
    }
    r = _run_git(["fetch", "origin", "main", "--quiet"])
    if r.returncode != 0:
        result["reason"] = (r.stderr or r.stdout or "fetch failed").strip()[:200]
        return result

    local = _run_git(["rev-parse", "HEAD"]).stdout.strip()
    remote = _run_git(["rev-parse", "origin/main"]).stdout.strip()
    if not local or not remote or remote == "0000000000000000000000000000000000000000":
        result["reason"] = "origin/main not found — is this a GitHub clone?"
        return result

    result["dirty"] = bool(_dirty_files())
    result["ok"] = True
    if local == remote:
        result["reason"] = "up to date"
        return result

    # Local commits the remote doesn't have? Then a pull can't help.
    ahead = _run_git(["rev-list", "--count", "origin/main..HEAD"])
    if ahead.returncode == 0 and (ahead.stdout or "").strip() not in ("", "0"):
        result["reason"] = "local commits not on GitHub — push instead"
        return result

    # Remote is ahead (possibly diverged, but nothing local to lose).
    show = _run_git(["show", "origin/main:config.py"])
    if show.returncode == 0:
        result["latest"] = _parse_version(show.stdout) or remote[:7]
    else:
        result["latest"] = remote[:7]
    result["available"] = True
    result["reason"] = f"v{result['latest']} is available"
    return result


def update() -> Dict[str, Any]:
    """Fast-forward to origin/main. Refuses over local edits/commits."""
    result: Dict[str, Any] = {
        "ok": False,
        "version": _local_version(),
        "reason": "",
    }
    dirty = _dirty_files()
    if dirty:
        result["reason"] = "local changes block the update: " + ", ".join(dirty[:3])
        return result

    ahead = _run_git(["rev-list", "--count", "origin/main..HEAD"])
    if ahead.returncode == 0 and (ahead.stdout or "").strip() not in ("", "0"):
        result["reason"] = "local commits not on GitHub — push first"
        return result

    r = _run_git(["pull", "--ff-only", "origin", "main"])
    if r.returncode != 0:
        result["reason"] = ((r.stderr or r.stdout or "pull failed").strip())[:200]
        return result

    combined = (r.stdout or "") + (r.stderr or "")
    if "Already up to date" in combined:
        result["ok"] = True
        result["reason"] = "already up to date"
        return result

    try:
        text = (ROOT / "config.py").read_text(encoding="utf-8")
        result["version"] = _parse_version(text) or result["version"]
    except Exception:
        pass
    result["ok"] = True
    result["reason"] = f"updated to v{result['version']} — restart JARVIS to finish"
    log.info("Self-update pulled v%s", result["version"])
    return result


def boot_check(auto: bool = True) -> None:
    """Non-blocking: fetch once at boot and, if allowed, pull the update."""
    import threading
    threading.Thread(target=_boot_check_sync, args=(auto,), daemon=True,
                     name="updater").start()


def _boot_check_sync(auto: bool = True) -> None:
    try:
        res = check()
        if not res.get("ok"):
            if res.get("reason"):
                log.info("Update check skipped: %s", res["reason"])
            return
        if not res.get("available"):
            return
        log.info("Update available: %s", res["reason"])
        try:
            from memory import get_pref
            auto_on = get_pref("auto_update", True)
        except Exception:
            auto_on = True
        if auto and auto_on and not res.get("dirty"):
            pulled = update()
            if pulled.get("ok"):
                _notify(f"JARVIS updated to v{pulled['version']}. "
                        "Restart to finish.")
            else:
                _notify(f"Auto-update failed: {pulled.get('reason')}")
        else:
            why = ("local changes block it" if res.get("dirty")
                   else "auto-update is off")
            _notify(f"JARVIS v{res['latest']} is available ({why}) — "
                    "Settings > ABOUT to update.")
    except Exception as exc:
        log.warning("Boot update check failed: %s", exc)


def _notify(message: str) -> None:
    try:
        from system import notify
        notify.alert(message)
    except Exception:
        log.info("%s", message)
