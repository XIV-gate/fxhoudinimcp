"""Houdini 22 character tools for KineFX skeletons and APEX graphs."""

from __future__ import annotations

# Built-in
from collections import Counter
from typing import Any

# Third-party
import hou

# Internal
from fxhoudinimcp_server.dispatcher import register_handler


def _get_sop_geometry(node_path: str) -> tuple[hou.Node, hou.Geometry]:
    node = hou.node(node_path)
    if node is None:
        raise ValueError(f"Node not found: {node_path}")
    try:
        geometry = node.geometry()
    except Exception as exc:
        raise ValueError(f"Could not cook SOP geometry at {node_path}: {exc}") from exc
    if geometry is None:
        raise ValueError(f"Node has no SOP geometry: {node_path}")
    return node, geometry


def _safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    try:
        return [_safe_value(item) for item in value.asTuple()]
    except Exception:
        pass
    try:
        return [_safe_value(item) for item in value]
    except Exception:
        return str(value)


def _point_value(point: hou.Point, attrib: hou.Attrib | None) -> Any:
    if attrib is None:
        return None
    try:
        return _safe_value(point.attribValue(attrib))
    except Exception:
        return None


def _vertex_value(vertex: hou.Vertex, attrib: hou.Attrib | None) -> Any:
    if attrib is None:
        return None
    try:
        return _safe_value(vertex.attribValue(attrib))
    except Exception:
        return None


def _hierarchy(geometry: hou.Geometry) -> tuple[dict[int, int], dict[int, list[int]]]:
    """Build KineFX parent/children maps from polygon vertex order."""
    parents: dict[int, int] = {}
    children: dict[int, list[int]] = {}
    for prim in geometry.prims():
        try:
            points = list(prim.points())
        except Exception:
            continue
        for parent_point, child_point in zip(points, points[1:], strict=False):
            parent = parent_point.number()
            child = child_point.number()
            parents.setdefault(child, parent)
            children.setdefault(parent, [])
            if child not in children[parent]:
                children[parent].append(child)
    return parents, children


def _skeleton_payload(
    node_path: str,
    joint_limit: int,
    include_transforms: bool,
) -> dict[str, Any]:
    node, geometry = _get_sop_geometry(node_path)
    limit = max(1, min(int(joint_limit), 5000))
    name_attrib = geometry.findPointAttrib("name")
    transform_attrib = geometry.findPointAttrib("transform")
    local_transform_attrib = geometry.findPointAttrib("localtransform")
    parents, children = _hierarchy(geometry)

    joints: list[dict[str, Any]] = []
    names: list[str] = []
    for point in geometry.points()[:limit]:
        index = point.number()
        name_value = _point_value(point, name_attrib)
        name = str(name_value) if name_value is not None else f"point_{index}"
        names.append(name)
        parent_index = parents.get(index)
        joint: dict[str, Any] = {
            "index": index,
            "name": name,
            "position": list(point.position()),
            "parent_index": parent_index,
            "child_indices": children.get(index, []),
        }
        if include_transforms:
            joint["transform"] = _point_value(point, transform_attrib)
            if local_transform_attrib is not None:
                joint["local_transform"] = _point_value(
                    point,
                    local_transform_attrib,
                )
        joints.append(joint)

    point_count = len(geometry.points())
    roots = [
        {"index": joint["index"], "name": joint["name"]}
        for joint in joints
        if joint["parent_index"] is None
    ]
    return {
        "node_path": node.path(),
        "node_type": node.type().name(),
        "is_kinefx_skeleton": (
            name_attrib is not None and transform_attrib is not None
        ),
        "joint_count": point_count,
        "returned_joint_count": len(joints),
        "truncated": point_count > limit,
        "has_name_attribute": name_attrib is not None,
        "has_transform_attribute": transform_attrib is not None,
        "root_joints": roots,
        "joints": joints,
        "_names": names,
        "_parents": parents,
    }


def _get_kinefx_skeleton(
    node_path: str,
    joint_limit: int = 500,
    include_transforms: bool = True,
    **_: Any,
) -> dict[str, Any]:
    """Inspect KineFX joints and hierarchy encoded by SOP point topology."""
    payload = _skeleton_payload(node_path, joint_limit, include_transforms)
    payload.pop("_names", None)
    payload.pop("_parents", None)
    return payload


def _validate_kinefx_skeleton(
    node_path: str,
    joint_limit: int = 5000,
    **_: Any,
) -> dict[str, Any]:
    """Validate required attributes, unique names, roots, and hierarchy cycles."""
    payload = _skeleton_payload(node_path, joint_limit, include_transforms=False)
    names = payload.pop("_names")
    parents = payload.pop("_parents")

    duplicate_names = sorted(
        name for name, count in Counter(names).items() if count > 1
    )
    cycles: list[list[int]] = []
    for start in parents:
        chain: list[int] = []
        seen: dict[int, int] = {}
        current = start
        while current in parents:
            if current in seen:
                cycle = chain[seen[current]:] + [current]
                if cycle not in cycles:
                    cycles.append(cycle)
                break
            seen[current] = len(chain)
            chain.append(current)
            current = parents[current]

    issues: list[dict[str, Any]] = []
    if not payload["has_name_attribute"]:
        issues.append({"code": "MISSING_NAME", "message": "Missing point name attribute"})
    if not payload["has_transform_attribute"]:
        issues.append({
            "code": "MISSING_TRANSFORM",
            "message": "Missing point transform attribute",
        })
    if duplicate_names:
        issues.append({
            "code": "DUPLICATE_NAMES",
            "message": "Joint names must be unique",
            "names": duplicate_names,
        })
    if cycles:
        issues.append({
            "code": "HIERARCHY_CYCLES",
            "message": "Hierarchy contains cycles",
            "cycles": cycles,
        })
    if payload["joint_count"] and not payload["root_joints"]:
        issues.append({
            "code": "NO_ROOT",
            "message": "No root joint was found from polygon vertex order",
        })

    return {
        "node_path": payload["node_path"],
        "valid": not issues,
        "joint_count": payload["joint_count"],
        "root_joints": payload["root_joints"],
        "issues": issues,
        "issue_count": len(issues),
        "truncated": payload["truncated"],
    }


def _get_apex_graph_info(
    node_path: str,
    node_limit: int = 500,
    connection_limit: int = 1000,
    **_: Any,
) -> dict[str, Any]:
    """Inspect an APEX graph's point nodes, ports, tags, and connections."""
    node, geometry = _get_sop_geometry(node_path)
    point_limit = max(1, min(int(node_limit), 5000))
    wire_limit = max(1, min(int(connection_limit), 10000))

    name_attrib = geometry.findPointAttrib("name")
    callback_attrib = geometry.findPointAttrib("callback")
    tags_attrib = geometry.findPointAttrib("tags")
    parms_attrib = geometry.findPointAttrib("parms")
    properties_attrib = geometry.findPointAttrib("properties")
    portname_attrib = geometry.findVertexAttrib("portname")
    portalias_attrib = geometry.findVertexAttrib("portalias")
    portindex_attrib = geometry.findVertexAttrib("portindex")

    graph_nodes: list[dict[str, Any]] = []
    for point in geometry.points()[:point_limit]:
        entry = {
            "index": point.number(),
            "name": _point_value(point, name_attrib),
            "callback": _point_value(point, callback_attrib),
            "tags": _point_value(point, tags_attrib) or [],
        }
        parms = _point_value(point, parms_attrib)
        properties = _point_value(point, properties_attrib)
        if isinstance(parms, dict):
            entry["parameter_names"] = sorted(parms)
        if isinstance(properties, dict):
            entry["property_names"] = sorted(properties)
        graph_nodes.append(entry)

    connections: list[dict[str, Any]] = []
    for prim in geometry.prims():
        vertices = list(prim.vertices())
        if len(vertices) < 2:
            continue
        endpoints = []
        for vertex in (vertices[0], vertices[-1]):
            point = vertex.point()
            endpoints.append({
                "node_index": point.number(),
                "node_name": _point_value(point, name_attrib),
                "port_name": _vertex_value(vertex, portname_attrib),
                "port_alias": _vertex_value(vertex, portalias_attrib),
                "port_index": _vertex_value(vertex, portindex_attrib),
            })
        connections.append({"primitive": prim.number(), "endpoints": endpoints})
        if len(connections) >= wire_limit:
            break

    detail_properties = None
    detail_name = None
    try:
        if geometry.findGlobalAttrib("properties") is not None:
            detail_properties = _safe_value(geometry.attribValue("properties"))
        if geometry.findGlobalAttrib("name") is not None:
            detail_name = _safe_value(geometry.attribValue("name"))
    except Exception:
        pass

    point_count = len(geometry.points())
    prim_count = len(geometry.prims())
    return {
        "node_path": node.path(),
        "node_type": node.type().name(),
        "is_apex_graph": name_attrib is not None and callback_attrib is not None,
        "graph_name": detail_name,
        "graph_properties": detail_properties,
        "graph_node_count": point_count,
        "connection_primitive_count": prim_count,
        "returned_graph_node_count": len(graph_nodes),
        "returned_connection_count": len(connections),
        "nodes_truncated": point_count > point_limit,
        "connections_truncated": prim_count > wire_limit,
        "graph_nodes": graph_nodes,
        "connections": connections,
    }


register_handler("character.get_kinefx_skeleton", _get_kinefx_skeleton)
register_handler("character.validate_kinefx_skeleton", _validate_kinefx_skeleton)
register_handler("character.get_apex_graph_info", _get_apex_graph_info)
