"""Tests for read-only and confirmation enforcement."""

from __future__ import annotations

# Built-in
import os
import sys
from unittest.mock import MagicMock

sys.modules.setdefault("hou", MagicMock())
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "houdini",
        "scripts",
        "python",
    ),
)

# Internal
import fxhoudinimcp_server.config as config  # noqa: E402
from fxhoudinimcp_server.policy import (  # noqa: E402
    authorize,
    is_read_only_command,
)


def _mode(monkeypatch, value: str) -> None:
    monkeypatch.setattr(config.hou, "getenv", lambda name: value)


def test_read_only_classification_fails_closed():
    assert is_read_only_command("nodes.get_node_info") is True
    assert is_read_only_command("help.search_help") is True
    assert is_read_only_command("nodes.create_node") is False
    assert is_read_only_command("future.unknown_action") is False


def test_read_only_mode_blocks_mutation(monkeypatch):
    _mode(monkeypatch, "read-only")

    _, error = authorize("nodes.create_node", {"node_type": "box"})

    assert error is not None
    assert error["error"]["code"] == "PERMISSION_ERROR"


def test_safe_mode_requires_explicit_confirmation(monkeypatch):
    _mode(monkeypatch, "safe")

    _, error = authorize("nodes.delete_node", {"node_path": "/obj/geo1"})
    params, allowed = authorize(
        "nodes.delete_node",
        {"node_path": "/obj/geo1", "confirm": True},
    )

    assert error is not None
    assert error["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert allowed is None
    assert params == {"node_path": "/obj/geo1"}


def test_full_mode_strips_confirmation_without_blocking(monkeypatch):
    _mode(monkeypatch, "full")

    params, error = authorize("code.execute_python", {"confirm": False, "code": "x=1"})

    assert error is None
    assert params == {"code": "x=1"}
