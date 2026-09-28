"""MCP (Model Context Protocol) server manager."""
from __future__ import annotations
import json
from pathlib import Path
from skills.registry import register
from logger import get_logger

log = get_logger(__name__)

_CONFIG = Path(__file__).resolve().parent.parent / "mcp_servers.json"


def _load() -> list[dict]:
    if not _CONFIG.exists():
        return []
    try:
        return json.loads(_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save(items: list[dict]) -> None:
    _CONFIG.write_text(json.dumps(items, indent=2), encoding="utf-8")


@register("mcp_add", [
    r"^add\s+mcp\s+server\s+(?P<name>\w+)\s+command\s+(?P<cmd>.+?)[\?\.\!]?$",
], "Add MCP server")
def s_add(text, m):
    name = m.group("name")
    cmd = m.group("cmd").strip()
    items = _load()
    items = [s for s in items if s.get("name") != name]
    items.append({"name": name, "command": cmd, "enabled": True})
    _save(items)
    return f"MCP server '{name}' added."


@register("mcp_list", [
    r"^(?:list|show)\s+mcp\s+servers?[\?\.\!]?$",
], "List MCP servers")
def s_list(text, m):
    items = _load()
    if not items:
        return "No MCP servers configured."
    lines = [f"{len(items)} MCP servers:"]
    for s in items:
        status = "on" if s.get("enabled") else "off"
        lines.append(f"- {s.get('name')} ({status})")
    return " ".join(lines)


@register("mcp_test", [
    r"^test\s+mcp\s+server\s+(?P<name>\w+)[\?\.\!]?$",
], "Test MCP server")
def s_test(text, m):
    name = m.group("name")
    items = _load()
    srv = next((s for s in items if s.get("name") == name), None)
    if not srv:
        return f"MCP server '{name}' not found."
    return f"MCP server '{name}' is configured (command: {srv.get('command')})."
