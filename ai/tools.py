"""Compatibility shim — re-exports from tool_schemas and tool_dispatch.

Kept so existing imports like `from ai.tools import TOOL_SCHEMAS`
and `from ai.tools import execute_tool` keep working.
"""

from ai.tool_schemas import TOOL_SCHEMAS
from ai.tool_dispatch import execute_tool, mcp_schemas

__all__ = ["TOOL_SCHEMAS", "execute_tool", "mcp_schemas"]
