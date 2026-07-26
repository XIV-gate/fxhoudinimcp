"""Tool-profile selection for controlling MCP schema size.

Profiles are resolved before FastMCP registers tools.  This keeps clients from
loading schemas for unrelated Houdini domains while preserving ``all`` as the
backwards-compatible default.
"""

from __future__ import annotations

# Built-in
import os

ALL_TOOL_MODULES = (
    "scene",
    "nodes",
    "graph",
    "help",
    "parameters",
    "code",
    "dops",
    "animation",
    "rendering",
    "viewport",
    "tops",
    "cops",
    "hda",
    "vex",
    "geometry",
    "lops",
    "context",
    "workflows",
    "materials",
    "chops",
    "cache",
    "takes",
    "audit",
    "character",
)

_CORE = {
    "scene",
    "nodes",
    "graph",
    "help",
    "parameters",
    "context",
    "viewport",
    "audit",
}

PROFILE_MODULES = {
    "core": _CORE,
    "sop": _CORE
    | {
        "geometry",
        "vex",
        "workflows",
        "materials",
        "cache",
        "hda",
        "character",
    },
    "solaris": _CORE | {"lops", "materials", "rendering", "hda"},
    "simulation": _CORE
    | {"dops", "tops", "workflows", "cache", "geometry", "rendering"},
    "copernicus": _CORE | {"cops"},
    "animation": _CORE | {"animation", "chops", "takes", "character"},
    "developer": _CORE | {"code", "hda", "vex"},
    "all": set(ALL_TOOL_MODULES),
}


def available_profiles() -> tuple[str, ...]:
    """Return supported profile names in stable display order."""
    return tuple(PROFILE_MODULES)


def active_profile_names(value: str | None = None) -> tuple[str, ...]:
    """Parse a profile expression such as ``sop,solaris``."""
    raw = value
    if raw is None:
        raw = os.getenv("FXHOUDINIMCP_TOOL_PROFILE", "all")
    names = tuple(
        dict.fromkeys(part.strip().lower() for part in raw.split(",") if part.strip())
    )
    if not names:
        names = ("all",)

    invalid = sorted(set(names) - PROFILE_MODULES.keys())
    if invalid:
        choices = ", ".join(available_profiles())
        raise ValueError(
            f"Unknown FXHOUDINIMCP_TOOL_PROFILE value(s): {', '.join(invalid)}. "
            f"Available profiles: {choices}"
        )
    return names


def active_tool_modules(value: str | None = None) -> tuple[str, ...]:
    """Resolve active profiles to an ordered, de-duplicated module list."""
    names = active_profile_names(value)
    selected: set[str] = set()
    for name in names:
        selected.update(PROFILE_MODULES[name])
    return tuple(module for module in ALL_TOOL_MODULES if module in selected)
