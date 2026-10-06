"""n8n Webhook & Event Bridge suite.

Inbound: `POST /api/webhook/in` — n8n (or any automation) delivers a
payload; JARVIS stores it, can announce it (toast + HUD flash +
speech) and can RUN its `text` through the skill router so an n8n flow
can trigger real system actions. Guarded three ways: disabled by
default, `X-Jarvis-Token` when a token is set, localhost-only when not.

Outbound: *"send to n8n: build green"* packages your line as JSON and
POSTs it to `webhook_out_url` (set with *"set n8n url ..."*). Uses
stdlib urllib — no extra dependency.
"""
from __future__ import annotations

import hmac
import json
import threading
import time
import urllib.request
from collections import deque
from typing import Any, Dict, Optional, Tuple

from logger import get_logger
from skills.registry import register

log = get_logger(__name__)

_lock = threading.Lock()
_recent: deque = deque(maxlen=50)
_id = 0

_LOCAL = ("127.0.0.1", "::1", "localhost")


def _prefs() -> tuple[bool, str, str]:
    try:
        from memory import get_pref
        enabled = bool(get_pref("webhook_enabled", False))
        token = (get_pref("webhook_token", "") or "").strip()
        out_url = (get_pref("webhook_out_url", "") or "").strip()
    except Exception:
        enabled, token, out_url = False, "", ""
    return enabled, token, out_url


def ingest(payload: Dict[str, Any], token_header: Optional[str],
           addr: Optional[str]) -> Tuple[Dict[str, Any], int]:
    """Validate + store one inbound webhook. Returns (body, http_code)."""
    enabled, token, _ = _prefs()
    if not enabled:
        return {"error": "Webhooks are disabled "
                "(Settings: webhook_enabled pref)."}, 403
    if token:
        if not token_header or not hmac.compare_digest(token_header, token):
            return {"error": "Bad or missing X-Jarvis-Token."}, 401
    elif (addr or "") not in _LOCAL:
        return {"error": "No token set — localhost only."}, 403
    if not isinstance(payload, dict):
        return {"error": "Payload must be a JSON object."}, 400
    text = str(payload.get("text") or "")[:2000]
    event = str(payload.get("event") or payload.get("source") or "webhook")[:80]
    data = payload.get("data")
    try:
        json.dumps(data)  # must be serialisable
    except Exception:
        data = {"raw": str(data)[:500]}

    global _id
    with _lock:
        _id += 1
        rec = {"id": _id, "ts": time.time(), "event": event,
               "text": text, "data": data, "ran": None, "spoke": False}
        _recent.append(rec)

    reply: Dict[str, Any] = {"ok": True, "id": _id, "event": event}
    if text and payload.get("speak"):
        rec["spoke"] = True
        try:
            from system import notify
            notify.alert(event, text)
        except Exception as exc:
            log.debug("webhook toast failed: %s", exc)
        try:
            from voice import speak_async
            speak_async(text)
        except Exception:
            pass
    if text and payload.get("run"):
        try:
            from skills import dispatch
            out = dispatch(text)
            rec["ran"] = out or "no skill matched"
            reply["ran"] = rec["ran"]
        except Exception as exc:
            rec["ran"] = f"error: {exc}"
            reply["ran"] = rec["ran"]
    log.info("webhook in: event=%s run=%s speak=%s",
             event, bool(payload.get("run")), bool(payload.get("speak")))
    return reply, 200


def recent(limit: int = 20) -> list[dict]:
    with _lock:
        items = list(_recent)[-limit:]
    items.reverse()
    return items


def send_now(text: str) -> Tuple[bool, str]:
    """POST a line to the configured n8n webhook."""
    _, _, url = _prefs()
    if not url:
        return False, ("No n8n URL set — say "
                       "'set n8n url https://...'.")
    body = json.dumps({
        "source": "jarvis",
        "text": text[:2000],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }).encode("utf-8")
    try:
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=10) as r:
            code = getattr(r, "status", 200)
        return True, f"Sent to n8n (HTTP {code})."
    except Exception as exc:
        return False, f"n8n send failed: {exc}"


@register("n8n", [
    r"^(?:please\s+)?(?:send|post|push)\s+(?:this\s+|it\s+)?(?:over\s+|to\s+)?n8n\s*[:,]?\s*(?P<body>.+?)[\?\.\!]?$",
    r"^n8n\s*[:,]\s*(?P<body>.+?)[\?\.\!]?$",
], "Send a line to your n8n webhook", front=True)
def skill_n8n_send(text, match):
    body = (match.group("body") or "").strip()
    if not body:
        return None
    ok, msg = send_now(body)
    return msg


@register("n8n_config", [
    r"^set\s+(?:the\s+)?n8n\s+(?:webhook\s+)?(?:url|endpoint)\s+(?P<url>https?://\S+)$",
], "Set the outbound n8n webhook URL", front=True)
def skill_n8n_url(text, match):
    from memory import set_pref
    url = match.group("url").rstrip(".,")
    set_pref("webhook_out_url", url)
    return f"n8n webhook URL saved: {url}. Say 'test n8n' to ping it."


@register("n8n_status", [
    r"^(?:(?:test|status|ping)\s+(?:the\s+)?n8n|n8n\s+(?:status|ping))"
    r"(?:\s+(?:webhook|bridge))?$",
], "Test or report the n8n bridge", front=True)
def skill_n8n_status(text, match):
    enabled, token, url = _prefs()
    if "test" in text.split()[0].lower() or text.startswith("test") \
            or text.startswith("ping"):
        ok, msg = send_now("JARVIS ping — bridge test.")
        return msg
    state = ("receiving (token set)" if token else
             "receiving (localhost only)") if enabled else "disabled"
    outbound = url or "not set"
    return (f"n8n bridge: inbound {state}, outbound -> {outbound}. "
            f"{len(recent(50))} events stored this session.")
