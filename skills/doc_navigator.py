"""Deep Web Intelligence — Doc Navigator.

*"docs for flask"* — skips the search-engine detour and pulls the real
documentation: PyPI metadata (summary + description + docs link) or a
GitHub README for `owner/repo` slugs, then a terse LLM brief over the
raw text (extractive fallback when keyless). One reply, source URL
included, no browser tab required.
"""
from __future__ import annotations

import json
import re
import urllib.request

from logger import get_logger
from skills.registry import register

log = get_logger(__name__)

_MAX_BODY = 3500


def _get(url: str, timeout: float = 8.0) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": "jarvis-doc-navigator/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _clean(text: str) -> str:
    text = re.sub(r"```.*?```", "[code]", text or "", flags=re.DOTALL)
    text = re.sub(r"[`*_#>|]{1,6}", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _pypi(pkg: str) -> dict | None:
    try:
        raw = _get(f"https://pypi.org/pypi/{pkg}/json")
        info = json.loads(raw).get("info") or {}
    except Exception as exc:
        log.debug("pypi miss for %s: %s", pkg, exc)
        return None
    urls = info.get("project_urls") or {}
    doc_url = (info.get("docs_url") or urls.get("Documentation")
               or urls.get("Docs") or urls.get("Home")
               or info.get("home_page") or "").strip()
    body = info.get("description") or info.get("summary") or ""
    return {"summary": (info.get("summary") or "").strip(),
            "body": _clean(body)[:_MAX_BODY],
            "url": doc_url or f"https://pypi.org/project/{pkg}/",
            "source": "PyPI"}


def _github(slug: str) -> dict | None:
    for branch in ("HEAD", "main", "master"):
        for name in ("README.md", "readme.md"):
            try:
                text = _get(f"https://raw.githubusercontent.com/"
                            f"{slug}/{branch}/{name}")
                if text.strip():
                    return {"summary": "", "body": _clean(text)[:_MAX_BODY],
                            "url": f"https://github.com/{slug}",
                            "source": "GitHub"}
            except Exception:
                continue
    return None


def gather(pkg: str) -> dict | None:
    pkg = pkg.strip().rstrip("/").strip("`")
    if "/" in pkg and " " not in pkg:
        found = _github(pkg) or _pypi(pkg.split("/")[-1])
    else:
        pkg = pkg.split()[0] if pkg else ""
        found = _pypi(pkg) or _github(pkg) if pkg else None
    return found


def _brief(pkg: str, doc: dict) -> str | None:
    """One LLM call over the doc excerpt. None when keyless/broken."""
    try:
        from ai.client import get_client
        c = get_client()
        source = doc.get("summary") or ""
        msgs = [
            {"role": "system",
             "content": ("You explain libraries tersely to a Python dev. "
                         "From the doc excerpt give: one line saying what it "
                         "is, then 3-5 '- ' usage points (minimal code hints). "
                         "No fluff, no preamble.")},
            {"role": "user",
             "content": f"Library: {pkg}\nSummary: {source}\n\n"
                        f"Docs:\n{doc.get('body', '')[:3000]}"[:5000]},
        ]
        out = []
        for kind, payload in c.stream(msgs):
            if kind == "content":
                out.append(payload)
        return "".join(out).strip() or None
    except Exception as exc:
        log.debug("doc brief skipped: %s", exc)
        return None


@register("doc_navigator", [
    r"^(?:please\s+)?(?:show\s+)?(?:me\s+)?(?:the\s+)?"
    r"(?:docs?|documentation)\s+(?:for|on|of)\s+(?P<pkg>\S+?)[\?\.\!]?$",
    r"^(?:please\s+)?(?:explain|summarize)\s+(?:the\s+)?"
    r"(?:docs?\s+for|documentation\s+for)\s+(?P<pkg>\S+?)[\?\.\!]?$",
], "Pull and summarize real library documentation")
def skill_docs(text, match):
    pkg = (match.group("pkg") or "").strip().rstrip(".,;:")
    if not pkg:
        return None
    doc = gather(pkg)
    if not doc:
        return (f"No docs found for '{pkg}' on PyPI or GitHub — "
                f"check the spelling or give me the owner/repo slug.")
    brief = _brief(pkg, doc)
    if not brief:
        head = doc.get("summary") or doc.get("body", "")[:400]
        brief = head.strip()
    reply = f"{pkg} ({doc['source']}):\n{brief}\nSource: {doc['url']}"
    return reply[:2400]
