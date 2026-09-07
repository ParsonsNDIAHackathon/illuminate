"""Serialise neo4j Graph objects into the subgraph shape the frontend draws."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from neo4j.graph import Node, Path, Relationship
from neo4j.time import Date, DateTime


def _clean(v: Any) -> Any:
    """JSON-safe conversion that also handles graph objects nested inside lists
    and maps (e.g. the nodes/relationships lists apoc.path.* procedures return)."""
    if isinstance(v, Node):
        return node_dict(v)
    if isinstance(v, Relationship):
        return rel_dict(v)
    if isinstance(v, Path):
        return {"nodes": [node_dict(n) for n in v.nodes], "edges": [rel_dict(r) for r in v.relationships]}
    if isinstance(v, (Date, DateTime, date, datetime)):
        return v.isoformat() if hasattr(v, "isoformat") else str(v)
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    return v


def node_dict(n: Node) -> dict:
    props = {k: _clean(v) for k, v in dict(n).items()}
    labels = list(n.labels)
    primary = next((l for l in ("Entity", "Person", "Category", "Location", "Artifact", "Claim") if l in labels), labels[0] if labels else "Node")
    return {
        "id": props.get("id") or n.element_id,
        "label": primary,
        "labels": labels,
        "name": props.get("name") or props.get("title") or props.get("id") or n.element_id,
        "props": props,
    }


def rel_dict(r: Relationship) -> dict:
    props = {k: _clean(v) for k, v in dict(r).items()}
    s, t = r.start_node, r.end_node
    return {
        "id": props.get("id") or r.element_id,
        "source": (s.get("id") if s is not None else None) or (s.element_id if s is not None else None),
        "target": (t.get("id") if t is not None else None) or (t.element_id if t is not None else None),
        "type": r.type,
        "props": props,
    }


def subgraph_from_graph(graph) -> dict:
    nodes = {}
    edges = {}
    for n in graph.nodes:
        d = node_dict(n)
        nodes[d["id"]] = d
    for r in graph.relationships:
        d = rel_dict(r)
        if d["source"] in nodes and d["target"] in nodes:
            edges[d["id"]] = d
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}


def rows_clean(records) -> list[dict]:
    out = []
    for rec in records:
        row = {}
        for k, v in rec.items():
            row[k] = _clean(v)
        out.append(row)
    return out


def merge_subgraphs(*graphs: dict) -> dict:
    nodes, edges = {}, {}
    for g in graphs:
        if not g:
            continue
        for n in g.get("nodes", []):
            nodes[n["id"]] = n
        for e in g.get("edges", []):
            edges[e["id"]] = e
    return {"nodes": list(nodes.values()), "edges": list(edges.values())}
