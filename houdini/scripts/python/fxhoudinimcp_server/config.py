"""Runtime configuration flags for the in-Houdini MCP server."""

from __future__ import annotations

# Built-in
import os

# Third-party
import hou

_FALSY = {"0", "false", "off", "no"}
_ACCESS_MODES = {"full", "safe", "read-only"}


def _houdini_env(name: str, default: str) -> str:
    """Read an environment variable with runtime ``hou.putenv`` support."""
    value = hou.getenv(name)
    if not isinstance(value, str):
        value = os.environ.get(name, default)
    return value


def auto_layout_enabled() -> bool:
    """Whether handlers may auto-arrange nodes in the network editor.

    Reads ``FXHOUDINIMCP_AUTO_LAYOUT`` via ``hou.getenv`` first (so it can
    be set in houdini.env or toggled at runtime with ``hou.putenv``), then
    falls back to the process environment. Defaults to enabled; set to
    ``0`` to preserve existing node layouts.
    """
    value = _houdini_env("FXHOUDINIMCP_AUTO_LAYOUT", "1")
    return value.strip().lower() not in _FALSY


def access_mode() -> str:
    """Return ``full``, ``safe``, or ``read-only`` access mode.

    ``safe`` requires explicit confirmation for high-risk commands.
    ``read-only`` rejects every command that may mutate Houdini or disk.
    """
    value = _houdini_env("FXHOUDINIMCP_ACCESS_MODE", "full").strip().lower()
    if value not in _ACCESS_MODES:
        choices = ", ".join(sorted(_ACCESS_MODES))
        raise ValueError(
            f"Invalid FXHOUDINIMCP_ACCESS_MODE '{value}'. Expected: {choices}"
        )
    return value


def journal_enabled() -> bool:
    """Whether mutating MCP commands are written to the activity journal."""
    value = _houdini_env("FXHOUDINIMCP_JOURNAL", "1")
    return value.strip().lower() not in _FALSY


def journal_path() -> str:
    """Return the expanded JSONL audit-log path."""
    configured = _houdini_env(
        "FXHOUDINIMCP_AUDIT_LOG",
        "$HOUDINI_USER_PREF_DIR/fxhoudinimcp/audit.jsonl",
    )
    return hou.text.expandString(configured)


def layout_if_enabled(node: hou.Node) -> None:
    """Lay out *node*'s children unless auto-layout is disabled."""
    if auto_layout_enabled():
        node.layoutChildren()
