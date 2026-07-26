"""Access-policy and persistent activity-journal handlers."""

from __future__ import annotations

# Built-in
from typing import Any

# Internal
from fxhoudinimcp_server.config import (
    access_mode,
    journal_enabled,
    journal_path,
)
from fxhoudinimcp_server.dispatcher import register_handler
from fxhoudinimcp_server.journal import clear, read_entries
from fxhoudinimcp_server.policy import HIGH_RISK_COMMANDS


def _get_access_policy(**_: Any) -> dict[str, Any]:
    return {
        "access_mode": access_mode(),
        "journal_enabled": journal_enabled(),
        "journal_path": journal_path(),
        "high_risk_commands": sorted(HIGH_RISK_COMMANDS),
    }


def _get_activity_journal(
    limit: int = 50,
    command_filter: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    entries = read_entries(limit=limit, command_filter=command_filter)
    return {
        "entry_count": len(entries),
        "entries": entries,
        "journal_path": journal_path(),
        "command_filter": command_filter,
    }


def _clear_activity_journal(**_: Any) -> dict[str, Any]:
    return clear()


register_handler("audit.get_access_policy", _get_access_policy)
register_handler("audit.get_activity_journal", _get_activity_journal)
register_handler("audit.clear_activity_journal", _clear_activity_journal)
