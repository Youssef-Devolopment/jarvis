"""WhatsApp via WhatsApp Cloud API or pywhatkit fallback."""
from __future__ import annotations
import os
import subprocess
import sys
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)


def _whatsapp_cloud(to: str, message: str) -> str | None:
    """Send via official WhatsApp Cloud API (requires token)."""
    import json
    import urllib.request
    token = os.getenv("WHATSAPP_TOKEN", "").strip()
    phone_id = os.getenv("WHATSAPP_PHONE_ID", "").strip()
    if not token or not phone_id:
        return None
    try:
        url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
        body = json.dumps({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": message},
        }).encode("utf-8")
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"WhatsApp sent to {to}."
    except Exception as exc:
        log.warning("WhatsApp Cloud failed: %s", exc)
        return None


def _whatsapp_pywhatkit(to: str, message: str) -> str | None:
    """Fallback via pywhatkit (opens browser, sends after delay)."""
    try:
        import pywhatkit
        pywhatkit.sendwhatmsg_instantly(
            phone_no=to, message=message,
            wait_time=15, tab_close=True, close_time=3)
        return f"WhatsApp sent to {to} (via browser)."
    except ImportError:
        return None
    except Exception as exc:
        log.warning("pywhatkit failed: %s", exc)
        return None


@register("whatsapp_send", [
    r"^(?:send|message)\s+(?:a\s+)?whatsapp\s+(?:to|message)\s+"
    r"(?P<phone>\+?\d[\d\s\-]{6,15})\s+(?:saying|that|:)\s+(?P<msg>.+?)[\?\.\!]?$",
    r"^(?:send|message)\s+(?P<phone2>\+?\d[\d\s\-]{6,15})\s+on\s+whatsapp\s+"
    r"(?P<msg2>.+?)[\?\.\!]?$",
], "Send WhatsApp message")
def s_whatsapp(text, m):
    gd = m.groupdict()
    phone = (gd.get("phone") or gd.get("phone2") or "").strip()
    msg = (gd.get("msg") or gd.get("msg2") or "").strip()
    if not phone or not msg:
        return None
    result = _whatsapp_cloud(phone, msg)
    if result:
        return result
    result = _whatsapp_pywhatkit(phone, msg)
    if result:
        return result
    return "WhatsApp not configured. Add WHATSAPP_TOKEN and WHATSAPP_PHONE_ID to .env."
