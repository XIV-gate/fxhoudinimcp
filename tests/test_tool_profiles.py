"""Tests for context-saving MCP tool profiles."""

from __future__ import annotations

# Third-party
import pytest

# Internal
from fxhoudinimcp.tool_profiles import (
    active_profile_names,
    active_tool_modules,
)


def test_all_profile_preserves_every_module():
    modules = active_tool_modules("all")

    assert "scene" in modules
    assert "code" in modules
    assert "character" in modules
    assert "audit" in modules


def test_profiles_can_be_composed_without_duplicates():
    modules = active_tool_modules("sop,solaris")

    assert "geometry" in modules
    assert "lops" in modules
    assert "scene" in modules
    assert "code" not in modules
    assert len(modules) == len(set(modules))


def test_profile_parser_normalizes_and_deduplicates():
    assert active_profile_names(" SOP,solaris,sop ") == ("sop", "solaris")


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError, match="Unknown FXHOUDINIMCP_TOOL_PROFILE"):
        active_tool_modules("sop,unknown")
