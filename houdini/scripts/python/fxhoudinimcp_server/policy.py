"""Server-side access policy for Houdini MCP commands."""

from __future__ import annotations

# Built-in
from typing import Any

# Internal
from fxhoudinimcp_server.config import access_mode

HIGH_RISK_COMMANDS = {
    "audit.clear_activity_journal",
    "cache.clear_cache",
    "cache.write_cache",
    "code.evaluate_expression",
    "code.execute_hscript",
    "code.execute_python",
    "hda.create_hda",
    "hda.install_hda",
    "hda.reload_hda",
    "hda.set_hda_section_content",
    "hda.uninstall_hda",
    "hda.update_hda",
    "nodes.delete_node",
    "rendering.render_node_network",
    "rendering.render_quad_view",
    "rendering.render_viewport",
    "rendering.start_render",
    "scene.export_file",
    "scene.load_scene",
    "scene.new_scene",
    "scene.save_scene",
    "viewport.capture_network_editor",
    "viewport.capture_screenshot",
}

_READ_ONLY_ACTION_PREFIXES = (
    "compare_",
    "explain_",
    "find_",
    "get_",
    "inspect_",
    "list_",
    "sample_",
    "search_",
    "validate_",
    "verify_",
)

def is_read_only_command(command: str) -> bool:
    """Conservatively classify a command as read-only.

    Unknown action names are treated as mutating. This makes read-only mode
    fail closed when new handlers are added.
    """
    action = command.rsplit(".", 1)[-1]
    return action.startswith(_READ_ONLY_ACTION_PREFIXES)


def authorize(
    command: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Authorize a command and strip the transport-only confirmation flag."""
    clean_params = dict(params)
    confirmed = clean_params.pop("confirm", False) is True
    mode = access_mode()

    if mode == "read-only" and not is_read_only_command(command):
        return clean_params, {
            "status": "error",
            "error": {
                "code": "PERMISSION_ERROR",
                "message": (
                    f"Command '{command}' is blocked by read-only mode. "
                    "Set FXHOUDINIMCP_ACCESS_MODE=safe or full to allow mutations."
                ),
                "access_mode": mode,
            },
        }

    if mode == "safe" and command in HIGH_RISK_COMMANDS and not confirmed:
        return clean_params, {
            "status": "error",
            "error": {
                "code": "CONFIRMATION_REQUIRED",
                "message": (
                    f"Command '{command}' requires confirm=true in safe mode."
                ),
                "access_mode": mode,
                "command": command,
            },
        }

    return clean_params, None
