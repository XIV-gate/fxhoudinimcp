"""MCP tools for Houdini 22 KineFX skeletons and APEX graphs."""

from __future__ import annotations

# Third-party
from mcp.server.fastmcp import Context

# Internal
from fxhoudinimcp.server import _get_bridge, mcp


@mcp.tool()
async def get_kinefx_skeleton(
    ctx: Context,
    node_path: str,
    joint_limit: int = 500,
    include_transforms: bool = True,
) -> dict:
    """Inspect KineFX joints, transforms, roots, and parent/child topology.

    KineFX skeletons are SOP points with ``name`` and ``transform`` point
    attributes; polygon vertex order defines the hierarchy.
    """
    bridge = _get_bridge(ctx)
    return await bridge.execute(
        "character.get_kinefx_skeleton",
        {
            "node_path": node_path,
            "joint_limit": joint_limit,
            "include_transforms": include_transforms,
        },
    )


@mcp.tool()
async def validate_kinefx_skeleton(
    ctx: Context,
    node_path: str,
    joint_limit: int = 5000,
) -> dict:
    """Check required KineFX attributes, duplicate joint names, roots, and cycles."""
    bridge = _get_bridge(ctx)
    return await bridge.execute(
        "character.validate_kinefx_skeleton",
        {"node_path": node_path, "joint_limit": joint_limit},
    )


@mcp.tool()
async def get_apex_graph_info(
    ctx: Context,
    node_path: str,
    node_limit: int = 500,
    connection_limit: int = 1000,
) -> dict:
    """Inspect APEX graph nodes, callbacks, tags, ports, and wire endpoints.

    In Houdini 22 an APEX graph is SOP geometry: points are graph nodes,
    line primitives are wires, and vertices carry port metadata.
    """
    bridge = _get_bridge(ctx)
    return await bridge.execute(
        "character.get_apex_graph_info",
        {
            "node_path": node_path,
            "node_limit": node_limit,
            "connection_limit": connection_limit,
        },
    )
