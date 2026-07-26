"""MCP tools for access-policy inspection and activity journaling."""

from __future__ import annotations

# Third-party
from mcp.server.fastmcp import Context

# Internal
from fxhoudinimcp.server import _get_bridge, mcp
from fxhoudinimcp.tool_profiles import (
    active_profile_names,
    active_tool_modules,
)


@mcp.tool()
async def get_access_policy(ctx: Context) -> dict:
    """Get the active full/safe/read-only policy and journal configuration."""
    bridge = _get_bridge(ctx)
    result = await bridge.execute("audit.get_access_policy", {})
    result["tool_profiles"] = list(active_profile_names())
    result["tool_modules"] = list(active_tool_modules())
    return result


@mcp.tool()
async def get_activity_journal(
    ctx: Context,
    limit: int = 50,
    command_filter: str | None = None,
) -> dict:
    """Read recent mutating MCP actions with compact before/after scene diffs.

    Args:
        limit: Number of recent entries, from 1 to 500.
        command_filter: Optional substring filter for command names.
    """
    bridge = _get_bridge(ctx)
    params: dict = {"limit": limit}
    if command_filter is not None:
        params["command_filter"] = command_filter
    return await bridge.execute("audit.get_activity_journal", params)


@mcp.tool()
async def clear_activity_journal(
    ctx: Context,
    confirm: bool = False,
) -> dict:
    """Delete the persistent activity journal.

    Args:
        confirm: Must be true when safe mode is active.
    """
    bridge = _get_bridge(ctx)
    return await bridge.execute(
        "audit.clear_activity_journal",
        {"confirm": confirm},
    )
