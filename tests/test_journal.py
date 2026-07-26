"""Tests for compact audit parameter handling and scene diffs."""

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
from fxhoudinimcp_server.journal import (  # noqa: E402
    _bounded_scene_nodes,
    diff_scene_states,
    sanitize_params,
)


def test_source_code_is_hashed_not_logged():
    result = sanitize_params(
        {
            "code": "print('secret-ish source')",
            "traceback": "Traceback: user source line",
            "node_path": "/obj/geo1",
            "api_token": "do-not-log",
        }
    )

    assert result["code"]["length"] > 0
    assert len(result["code"]["sha256"]) == 64
    assert len(result["traceback"]["sha256"]) == 64
    assert result["api_token"] == "[redacted]"
    assert result["node_path"] == "/obj/geo1"


def test_scene_diff_reports_structure_wires_and_parameters():
    before = {
        "nodes": {
            "/obj/a": {"type": "box", "inputs": []},
            "/obj/b": {"type": "xform", "inputs": ["/obj/a"]},
        },
        "targets": {"/obj/a": {"params": {"sizex": 1}}},
        "truncated": False,
    }
    after = {
        "nodes": {
            "/obj/a": {"type": "box", "inputs": []},
            "/obj/b": {"type": "xform", "inputs": [None]},
            "/obj/c": {"type": "null", "inputs": ["/obj/a"]},
        },
        "targets": {"/obj/a": {"params": {"sizex": 2}}},
        "truncated": False,
    }

    diff = diff_scene_states(before, after)

    assert diff["nodes_added"] == ["/obj/c"]
    assert diff["nodes_rewired"] == ["/obj/b"]
    assert diff["parameter_changes"][0]["changes"]["sizex"] == {
        "old": 1,
        "new": 2,
    }


def test_scene_walk_stops_at_limit_without_expanding_whole_tree():
    class Node:
        def __init__(self, children=None):
            self._children = children or []

        def children(self):
            return self._children

    root = Node([Node([Node()]), Node(), Node()])

    nodes, truncated = _bounded_scene_nodes(root, 2)

    assert len(nodes) == 2
    assert truncated is True
