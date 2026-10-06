"""Operational health — one snapshot of every subsystem.

GET /api/health and Settings > SYSTEM read this module. Probes are cheap
(local state only, never network) and fail independently: a broken probe
reports status "unknown" instead of taking the endpoint down.

Boot paths (run.py, system/launcher.py) start services through
system.services, which records every result there; mark() remains for
marks with no registry entry (e.g. the desktop Flask thread) and for
legacy callers. Both feed _services_snapshot().
"""
from __future__ import annotations

import threading
import time
from typing import Any, Dict

from logger import get_logger

log = get_logger("health")

_lock = threading.Lock()
_services: Dict[str, Dict[str, Any]] = {}
_started_at = time.time()

# Worst-status ranking: 0 healthy, 1 attention, 2 broken.
_RANK = {"ok": 0, "info": 0, "warn": 1, "unknown": 1, "degraded": 2}
_ORDER = {0: "ok", 1: "warn", 2: "degraded"}


def mark(name: str, ok: bool, detail: str = "") -> None:
    """Record boot-time service state (called from run.py / launcher)."""
    with _lock:
        _services[name] = {"ok": bool(ok), "detail": str(detail)[:200]}


def reset() -> None:
    """Clear marks + registry results and restart the uptime clock (tests)."""
    global _started_at
    with _lock:
        _services.clear()
    try:
        from system import services as _svc
        _svc.reset()
    except Exception:
        pass
    _started_at = time.time()


def _services_snapshot() -> Dict[str, Any]:
    with _lock:
        items = {k: dict(v) for k, v in _services.items()}
    # Registry results (system.services) carry group + start timing and
    # win over a plain mark for the same name; mark-only entries (the
    # desktop Flask thread, legacy callers) still show up unchanged.
    try:
        from system import services as _svc
        for name, rec in _svc.results().items():
            merged = dict(rec)
            if not merged.get("detail"):
                merged["detail"] = (items.get(name) or {}).get("detail", "")
            items[name] = merged
    except Exception:
        pass
    if not items:
        return {"status": "unknown",
                "detail": "no boot marks recorded yet", "items": {}}
    failed = [k for k, v in items.items() if not v.get("ok")]
    detail = f"{len(items)} services tracked"
    if failed:
        detail += f" · {len(failed)} failed: " + ", ".join(failed[:4])
    return {"status": "degraded" if failed else "ok",
            "detail": detail, "items": items}


def _probe_config() -> dict:
    from config import try_settings, audit_settings
    s = try_settings()
    if s is None:
        return {"status": "warn",
                "detail": "settings unreadable (.env missing or invalid)"}
    warns = audit_settings(s)
    if warns:
        return {"status": "warn",
                "detail": f"{len(warns)} config warning(s)",
                "warnings": warns}
    return {"status": "ok", "detail": "no drift detected"}


def _probe_key() -> dict:
    from config import key_status, masked_key
    st = key_status()
    if st.get("ok"):
        return {"status": "ok",
                "detail": f"configured ({masked_key() or 'key'})"}
    return {"status": "warn", "detail": st.get("error") or "no API key"}


def _probe_memory() -> dict:
    try:
        import memory
        facts = len(memory.all_facts())
    except Exception as exc:
        return {"status": "degraded",
                "detail": f"memory unavailable: {exc}"[:160]}
    try:
        from memory import schema
        sch = schema.status()
    except Exception as exc:
        sch = {"ok": False, "detail": f"schema check failed: {exc}"[:120]}
    status = "ok" if sch.get("ok") else "warn"
    return {"status": status,
            "detail": f"{facts} facts · schema {sch.get('detail', '?')}",
            "facts": facts, "schema": sch}


def _probe_voice() -> dict:
    from config import try_settings
    s = try_settings()
    if s is None or not s.voice_name:
        return {"status": "warn", "detail": "no voice configured"}
    detail = f"{s.voice_name} · rate {s.voice_rate}"
    if not (s.groq_api_key or "").strip():
        detail += " · no Groq key (voice input off)"
    return {"status": "ok", "detail": detail, "voice": s.voice_name}


def _probe_guard() -> dict:
    from system import guard
    st = guard.status()
    detail = (f"{'on' if st.get('enabled') else 'off'} · "
              f"{st.get('percent', '-')}% RAM "
              f"(threshold {st.get('threshold', '-')}%) · "
              f"fired {st.get('fired', 0)}x")
    return {"status": "ok", "detail": detail,
            "enabled": st.get("enabled"),
            "percent": st.get("percent"),
            "threshold": st.get("threshold"),
            "fired": st.get("fired", 0)}


def _probe_updater() -> dict:
    from system import updater
    last = updater.last_check()
    if not last:
        return {"status": "unknown", "detail": "no update check yet this session"}
    if not last.get("ok"):
        return {"status": "warn",
                "detail": last.get("reason") or "update check failed"}
    if last.get("available"):
        return {"status": "info",
                "detail": f"v{last.get('latest')} available"}
    return {"status": "ok", "detail": "up to date"}


def _probe_mcp() -> dict:
    from mcp import runtime
    names = runtime.running_names()
    detail = f"{len(names)} running"
    if names:
        detail += ": " + ", ".join(str(n) for n in names[:4])
    return {"status": "ok", "detail": detail, "running": names}


def _probe_pending() -> dict:
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "logs" / "auto_skills" / "pending.json"
    if not p.exists():
        return {"status": "ok", "detail": "no pending verdicts"}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        count = len(data) if isinstance(data, (list, dict)) else 0
    except Exception:
        return {"status": "unknown", "detail": "pending.json unreadable"}
    if count:
        return {"status": "info",
                "detail": f"{count} skill draft(s) awaiting your verdict"}
    return {"status": "ok", "detail": "no pending verdicts"}


# Optional runtime dependencies — everything here can be missing while
# the app still boots (flask/dotenv are load-time fatal, so they would
# never be observable anyway).
_DEPS = {
    "playwright": "browser automation",
    "sounddevice": "mic input",
    "pystray": "system tray",
    "pynput": "global hotkeys",
    "pygame": "voice playback",
    "apscheduler": "briefings/scheduler",
    "psutil": "guard/time tracking",
}


def _has_module(name: str):
    """True/False if findable, None when the check itself failed."""
    import importlib.util
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return None


def _probe_deps() -> dict:
    missing, unknown = [], []
    for mod in _DEPS:
        found = _has_module(mod)
        if found is None:
            unknown.append(mod)
        elif not found:
            missing.append(mod)
    if missing:
        detail = "missing: " + ", ".join(missing)
        if unknown:
            detail += " · check failed: " + ", ".join(unknown)
        return {"status": "warn", "detail": detail[:160], "missing": missing}
    if unknown:
        return {"status": "unknown",
                "detail": "check failed: " + ", ".join(unknown)[:120]}
    return {"status": "ok",
            "detail": f"all {len(_DEPS)} optional dependencies present"}


def _probe_model() -> dict:
    from config import try_settings
    s = try_settings()
    if s is None:
        return {"status": "unknown", "detail": "settings unreadable"}
    if not (s.model or "").strip():
        return {"status": "warn", "detail": "no model configured"}
    base = (s.base_url or "").strip().rstrip("/")
    host = base.split("//", 1)[-1].split("/", 1)[0] or "api.deepseek.com"
    detail = (f"{s.model} @ {host} · temp {s.temperature} · "
              f"{len(s.providers or ())} extra provider(s)")
    return {"status": "ok", "detail": detail,
            "model": s.model, "base_host": host}


_PROBES = {
    "config": _probe_config,
    "model": _probe_model,
    "api_key": _probe_key,
    "deps": _probe_deps,
    "memory": _probe_memory,
    "voice": _probe_voice,
    "guard": _probe_guard,
    "updater": _probe_updater,
    "mcp": _probe_mcp,
    "pending_skills": _probe_pending,
}


def snapshot() -> Dict[str, Any]:
    """Full health snapshot for /api/health and the SYSTEM tab."""
    from config import VERSION
    checks: Dict[str, Any] = {}
    worst = 0
    for name, fn in _PROBES.items():
        try:
            res = dict(fn() or {})
        except Exception as exc:
            res = {"status": "unknown", "detail": f"probe failed: {exc}"[:160]}
        res.setdefault("status", "unknown")
        checks[name] = res
        worst = max(worst, _RANK.get(res["status"], 1))
    services = _services_snapshot()
    checks["services"] = services
    if services.get("items"):
        worst = max(worst, _RANK.get(services["status"], 1))
    overall = _ORDER[worst]
    return {"ok": worst == 0, "overall": overall, "version": VERSION,
            "uptime_s": int(time.time() - _started_at), "checks": checks}
