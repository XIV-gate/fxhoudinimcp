"""Persistent activity journal with lightweight Houdini scene diffs."""

from __future__ import annotations

# Built-in
import hashlib
import json
import os
from collections import deque
from datetime import datetime, timezone
from typing import Any

# Third-party
import hou

# Internal
from fxhoudinimcp_server.config import journal_enabled, journal_path

_NODE_LIMIT = 2000
_TARGET_LIMIT = 50
_ENTRY_CACHE: deque[dict[str, Any]] = deque(maxlen=500)
_SENSITIVE_MARKERS = ("password", "secret", "token", "api_key", "private_key")
_LARGE_CONTENT_KEYS = {"code", "content", "snippet", "traceback", "vex_code"}


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    try:
        return list(value)
    except Exception:
        return str(value)


def sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Remove secrets and replace large source payloads with hashes."""
    sanitized: dict[str, Any] = {}
    for key, value in params.items():
        lower = key.lower()
        if lower in _SENSITIVE_MARKERS or any(
            lower.endswith(f"_{marker}") for marker in _SENSITIVE_MARKERS
        ):
            sanitized[key] = "[redacted]"
            continue
        if lower in _LARGE_CONTENT_KEYS and isinstance(value, str):
            sanitized[key] = {
                "length": len(value),
                "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
            }
            continue
        safe = _json_safe(value)
        encoded = json.dumps(safe, ensure_ascii=False)
        sanitized[key] = safe if len(encoded) <= 2000 else "[truncated]"
    return sanitized


def _target_paths(params: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key, value in params.items():
        if key.endswith("_path") or key in {"parent_path", "dest_parent"}:
            values = value if isinstance(value, list) else [value]
            for item in values:
                if isinstance(item, str) and item.startswith("/") and item not in paths:
                    paths.append(item)
                    if len(paths) >= _TARGET_LIMIT:
                        return paths
    return paths


def _parm_state(node: hou.Node) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for parm in node.parms():
        try:
            if parm.isAtDefault():
                continue
            values[parm.name()] = _json_safe(parm.eval())
        except Exception:
            continue
    return values


def _bounded_scene_nodes(
    root: hou.Node,
    limit: int,
) -> tuple[list[hou.Node], bool]:
    """Breadth-first scene walk that stops without materializing every node."""
    try:
        queue = deque(root.children())
    except Exception:
        return [], False
    nodes: list[hou.Node] = []
    while queue and len(nodes) < limit:
        node = queue.popleft()
        nodes.append(node)
        try:
            queue.extend(node.children())
        except Exception:
            continue
    return nodes, bool(queue)


def capture_scene_state(params: dict[str, Any]) -> dict[str, Any]:
    """Capture structure globally and parameters for explicitly targeted nodes."""
    root = hou.node("/")
    nodes: dict[str, dict[str, Any]] = {}
    truncated = False
    if root is not None:
        scene_nodes, truncated = _bounded_scene_nodes(root, _NODE_LIMIT)
        for node in scene_nodes:
            try:
                nodes[node.path()] = {
                    "type": node.type().name(),
                    "inputs": [
                        item.path() if item is not None else None
                        for item in node.inputs()
                    ],
                }
            except Exception:
                continue

    targets: dict[str, dict[str, Any]] = {}
    for path in _target_paths(params):
        node = hou.node(path)
        if node is None:
            continue
        try:
            targets[path] = {
                "type": node.type().name(),
                "params": _parm_state(node),
            }
        except Exception:
            continue

    return {
        "nodes": nodes,
        "targets": targets,
        "truncated": truncated,
    }


def diff_scene_states(
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> dict[str, Any]:
    """Return a compact structural and targeted-parameter diff."""
    if before is None or after is None:
        return {"available": False}

    before_nodes = before.get("nodes", {})
    after_nodes = after.get("nodes", {})
    before_paths = set(before_nodes)
    after_paths = set(after_nodes)

    added = sorted(after_paths - before_paths)
    removed = sorted(before_paths - after_paths)
    rewired = sorted(
        path
        for path in before_paths & after_paths
        if before_nodes[path].get("inputs") != after_nodes[path].get("inputs")
    )

    before_targets = before.get("targets", {})
    after_targets = after.get("targets", {})
    parameter_changes: list[dict[str, Any]] = []
    for path in sorted(set(before_targets) | set(after_targets)):
        old = before_targets.get(path, {}).get("params", {})
        new = after_targets.get(path, {}).get("params", {})
        if old == new:
            continue
        changes: dict[str, dict[str, Any]] = {}
        for name in sorted(set(old) | set(new)):
            if old.get(name) != new.get(name):
                changes[name] = {"old": old.get(name), "new": new.get(name)}
        parameter_changes.append({"path": path, "changes": changes})

    cap = 200
    return {
        "available": True,
        "nodes_added": added[:cap],
        "nodes_added_count": len(added),
        "nodes_removed": removed[:cap],
        "nodes_removed_count": len(removed),
        "nodes_rewired": rewired[:cap],
        "nodes_rewired_count": len(rewired),
        "parameter_changes": parameter_changes[:cap],
        "parameter_changes_count": len(parameter_changes),
        "truncated": (
            before.get("truncated", False)
            or after.get("truncated", False)
            or len(added) > cap
            or len(removed) > cap
            or len(rewired) > cap
            or len(parameter_changes) > cap
        ),
    }


def record(
    command: str,
    params: dict[str, Any],
    success: bool,
    timing_ms: float,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
    error: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Append one command entry to memory and the JSONL audit log."""
    if not journal_enabled():
        return None

    entry: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "command": command,
        "success": success,
        "timing_ms": round(timing_ms, 2),
        "hip_file": hou.hipFile.name(),
        "params": sanitize_params(params),
        "diff": diff_scene_states(before, after),
    }
    if error:
        entry["error"] = sanitize_params(error)

    _ENTRY_CACHE.append(entry)
    try:
        path = journal_path()
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def read_entries(
    limit: int = 50,
    command_filter: str | None = None,
) -> list[dict[str, Any]]:
    """Read recent journal entries, including entries from prior sessions."""
    bounded_limit = max(1, min(int(limit), 500))
    entries: deque[dict[str, Any]] = deque(maxlen=bounded_limit)
    try:
        with open(journal_path(), encoding="utf-8") as stream:
            for line in stream:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if command_filter and command_filter.lower() not in str(
                    entry.get("command", "")
                ).lower():
                    continue
                entries.append(entry)
        return list(entries)
    except OSError:
        cached = list(_ENTRY_CACHE)
        if command_filter:
            cached = [
                item
                for item in cached
                if command_filter.lower() in str(item.get("command", "")).lower()
            ]
        return cached[-bounded_limit:]


def clear() -> dict[str, Any]:
    """Clear in-memory and on-disk journal entries."""
    _ENTRY_CACHE.clear()
    path = journal_path()
    removed = False
    try:
        if os.path.exists(path):
            os.remove(path)
            removed = True
    except OSError:
        pass
    return {"cleared": True, "file_removed": removed, "path": path}
