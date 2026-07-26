"""MCP tool modules for FXHoudini-MCP.

Importing this package registers all MCP tools with the FastMCP server.
Each submodule uses the `@mcp.tool()` decorator at import time.
"""

from __future__ import annotations

# Built-in
import importlib
import json

# Third-party
from mcp.types import ImageContent, TextContent


def result_with_image(result: dict) -> list[TextContent | ImageContent]:
    """Convert a handler result dict into MCP content blocks.

    If the result contains ``image_base64``, an ``ImageContent`` block is
    appended so that MCP clients (e.g. Claude Desktop) can display the
    image inline.  The base64 key is removed from the metadata text.
    """
    image_data = result.pop("image_base64", None)
    mime_type = result.pop("mime_type", "image/png")

    content: list[TextContent | ImageContent] = [
        TextContent(type="text", text=json.dumps(result)),
    ]

    if image_data:
        content.append(
            ImageContent(type="image", data=image_data, mimeType=mime_type)
        )

    return content


# Internal
from fxhoudinimcp.tool_profiles import (  # noqa: E402
    active_profile_names,
    active_tool_modules,
)

ACTIVE_TOOL_PROFILES = active_profile_names()
ACTIVE_TOOL_MODULES = active_tool_modules()

for _module_name in ACTIVE_TOOL_MODULES:
    importlib.import_module(f".{_module_name}", __package__)
