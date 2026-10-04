"""Add ANYTHING: sites, MCP servers, apps, skills — one verb."""
from __future__ import annotations
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

ADD_PATTERNS = [
    r"^(?:add|pin|save)\s+\S.*\s+as\s+(?:an?\s+)?"
    r"(?:site|bookmark|shortcut|app)[\?\.\!]?$",
    r"^(?:remember|bookmark)\s+https?://\S+\s+as\s+.+?[\?\.\!]?$",
    r"^(?:remove|forget|delete)\s+(?:the\s+)?site\s+.+?[\?\.\!]?$",
    r"^(?:add|install|setup)\s+mcp\s+\S.*$",
    r"^add\s+(?:a\s+)?skill\s+(?:that|to|for)\s+.+?[\?\.\!]?$",
]


@register("add_anything", ADD_PATTERNS,
          "Add sites, MCP servers, apps and skills")
def skill_add(text, m):
    try:
        from system import adder
        return adder.add(text)
    except Exception as exc:
        log.warning("add-anything failed: %s", exc)
        return None
