"""URL cleaner — remove tracking params."""

from __future__ import annotations
import re
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "dclid", "msclkid", "yclid", "mc_eid",
    "_ga", "_gl", "ref", "ref_src", "ref_url", "source",
    "igshid", "si", "feature", "spm", "scm",
}


def clean(url):
    if not url: return url
    try:
        p = urlparse(url)
        if not p.scheme: return url
        params = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                  if k.lower() not in TRACKING_PARAMS]
        cleaned = p._replace(query=urlencode(params))
        return urlunparse(cleaned)
    except Exception:
        return url


def clean_clipboard():
    try:
        import pyperclip
        raw = pyperclip.paste() or ""
    except ImportError:
        return {"ok": False, "error": "pyperclip not installed"}
    if not re.match(r"^https?://", raw.strip()):
        return {"ok": False, "error": "clipboard is not a URL"}
    cleaned = clean(raw.strip())
    try:
        import pyperclip
        pyperclip.copy(cleaned)
    except Exception:
        return {"ok": False, "error": "could not write clipboard"}
    return {"ok": True, "before": raw[:200], "after": cleaned[:200]}
