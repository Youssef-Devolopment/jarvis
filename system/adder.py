"""Add ANYTHING with one verb: sites, MCP servers, apps, skills.

Chat (`add ...`) and `POST /api/add` share this router. Unknown
shapes return None so dispatch falls through to other skills.
Every branch reuses the existing validated backend — this file adds
routing only, no new safety semantics.
"""
from __future__ import annotations
import re
from logger import get_logger

log = get_logger(__name__)

_PATTERNS = [
    # sites
    r"^(?:add|pin|save)\s+(.+?)\s+as\s+(?:an?\s+)?(?:site|bookmark|shortcut)[\?\.\!]?$",
    r"^(?:remember|bookmark)\s+(https?://\S+)\s+as\s+(.+?)[\?\.\!]?$",
    r"^(?:remove|forget|delete)\s+(?:the\s+)?site\s+(.+?)[\?\.\!]?$",
    # mcp
    r"^(?:add|install|setup)\s+mcp\s+(?:preset\s+)?([a-z0-9][a-z0-9_-]*)[\?\.\!]?$",
    r"^add\s+mcp\s+server\s+(?:named\s+)?(\w+)\s+(?:running|with\s+command|command\s+is)\s+(.+?)[\?\.\!]?$",
    # apps (learn without launching)
    r"^add\s+(.+?)\s+as\s+(?:an?\s+)?app[\?\.\!]?$",
    # skills (force a draft)
    r"^add\s+(?:a\s+)?skill\s+(?:that|to|for)\s+(.+?)[\?\.\!]?$",
]


def _add_site_as(name: str) -> str | None:
    return None


def _stem_of_url(url: str) -> str:
    host = (url.split("://", 1)[-1].split("/")[0].split(":")[0]
            .lower().lstrip("."))
    if host.startswith("www."):
        host = host[4:]
    return host.split(".")[0] if host else ""


def add(text: str) -> str | None:
    """Route an add-command. None = not an add-command, carry on."""
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()

    m = re.match(r"^(?:add|pin|save)\s+(https?://\S+)\s+as\s+(.+?)"
                 r"[\?\.\!]?$", t, re.IGNORECASE)
    if m:
        from system import launch as L
        return L.pin_site(m.group(2), m.group(1))
    m = re.match(r"^(?:add|pin|save)\s+(.+?)\s+as\s+(?:an?\s+)?"
                 r"(site|bookmark|shortcut)[\?\.\!]?$", t, re.IGNORECASE)
    if m:
        from system import launch as L
        candidate = m.group(1).strip()
        low = candidate.lower()
        if low.startswith(("http://", "https://")) or re.match(
                r"^[\w\-]+(\.[\w\-]+)+([/?#].*)?$", candidate, re.IGNORECASE):
            url = candidate if low.startswith(("http://", "https://")) \
                else "https://" + candidate
            return L.pin_site(_stem_of_url(url) or candidate, url)
        return ("Give me the address like this: "
                f"'remember <url> as {candidate}'.")
    m = re.match(r"^(?:remember|bookmark)\s+(https?://\S+)\s+as\s+(.+?)"
                 r"[\?\.\!]?$", t, re.IGNORECASE)
    if m:
        from system import launch as L
        return L.pin_site(m.group(2), m.group(1))
    m = re.match(r"^(?:remove|forget|delete)\s+(?:the\s+)?site\s+(.+?)"
                 r"[\?\.\!]?$", t, re.IGNORECASE)
    if m:
        from system import launch as L
        return L.unpin_site(m.group(1))

    if re.match(r"^(?:add|install|setup)\s+mcp\s+", low):
        return _add_mcp(t)
    if re.match(r"^add\s+.+\s+as\s+(?:an?\s+)?app[\?\.\!]?\s*$", low):
        m2 = re.match(r"^add\s+(.+?)\s+as\s+(?:an?\s+)?app[\?\.\!]?\s*$",
                      t, re.IGNORECASE)
        if m2:
            return _add_app(m2.group(1))
    m = re.match(r"^add\s+(?:a\s+)?skill\s+(?:that|to|for)\s+(.+?)"
                 r"[\?\.\!]?$", t, re.IGNORECASE)
    if m:
        return _add_skill(m.group(1))
    return None


def _add_mcp(t: str) -> str | None:
    m = re.match(r"^add\s+mcp\s+server\s+(?:named\s+)?(\w+)\s+"
                 r"(?:running|with\s+command|command\s+is)\s+(.+?)"
                 r"[\?\.\!]?$", t, re.IGNORECASE)
    if m:
        name, rest = m.group(1), m.group(2).strip()
        parts = rest.split(None, 1)
        cmd, args = parts[0], (parts[1] if len(parts) > 1 else "")
        try:
            from mcp import manager as _mm
            res = _mm.add_server(name, cmd, args)
        except Exception as exc:
            return f"Could not add that MCP server: {exc}"[:160]
        if isinstance(res, dict) and res.get("error"):
            return f"Could not add that MCP server: {res['error']}"[:160]
        return (f"MCP server '{name}' added. Start it from the MCP tab "
                f"or POST /api/mcp/start.")
    m = re.match(r"^(?:add|install|setup)\s+mcp\s+(?:preset\s+)?"
                 r"([a-z0-9][a-z0-9_-]*)[\?\.\!]?$", t, re.IGNORECASE)
    if not m:
        return None
    pid = m.group(1).lower()
    try:
        from mcp import presets as _mp
    except Exception as exc:
        return f"Could not load MCP presets: {exc}"[:160]
    try:
        known = [p["id"] for p in _mp.list_presets()]
    except Exception:
        known = []
    if pid not in known:
        avail = ", ".join(sorted(known)) if known else "none listed"
        return f"Unknown preset '{pid}'. Available: {avail}."
    try:
        res = _mp.install_preset(pid)
    except Exception as exc:
        return f"Preset install failed: {exc}"[:160]
    if isinstance(res, dict) and res.get("error"):
        return f"Preset install failed: {res['error']}"[:160]
    needs = (res.get("needs") or "nothing extra") if isinstance(res, dict) else ""
    return (f"MCP preset '{pid}' installed (needs: {needs}). Start it "
            f"from the MCP tab or POST /api/mcp/start.")


def _add_app(query: str) -> str:
    try:
        from system import app_learner
        from system.app_learner import _norm
        from skills.registry import get_skill
    except Exception as exc:
        return f"Could not learn that app: {exc}"[:160]
    try:
        hit = app_learner.find(query)
        if not hit:
            apps = app_learner.scan(force=True)
            hit = apps.get(_norm(query))
        if not hit:
            return f"Could not find an app called '{query}'."
        skill, created = app_learner.ensure_skill(hit["name"], hit["path"])
        live = bool(get_skill(skill))
        if live:
            return (f"Learned '{hit['name']}' — say 'open {hit['name']}' "
                    f"anytime.")
        return (f"Learned '{hit['name']}' — skill drafted, say "
                f"'approve skill {skill}' to enable it.")
    except ValueError as exc:
        return str(exc)[:160]
    except Exception as exc:
        log.warning("add app failed: %s", exc)
        return "Could not learn that app right now."


def _add_skill(request: str) -> str:
    request = (request or "").strip()
    if not request:
        return None
    try:
        from skills import auto_generator as _ag
        proposal = _ag.propose_skill(request)
        return _ag.approval_prompt(proposal)
    except Exception as exc:
        log.debug("add skill draft failed: %s", exc)
        return ("Couldn't draft that skill "
                "(an API key is needed for drafting).")
