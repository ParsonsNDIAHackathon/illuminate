"""Graph change notifications.

A committed write is the only thing that changes the graph, so every one of them
announces the nodes it touched. Open canvases merge the announced delta instead of
waiting for a reload, so an entity added from chat — or a relationship enrichment
commits — appears while the user is looking at the graph.

The delta carries the touched nodes *plus one hop*, so a new node arrives already
attached to whatever it was connected to rather than as an orphan the client would
have to fetch a second time.
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Iterable

from . import db
from .graphio import subgraph_from_graph

Listener = Callable[[str, dict], Awaitable[None]]

_listeners: set[Listener] = set()

# Node ids are prefixed by kind (see ids.py). Relationship ids (rel_) are deliberately
# absent: this matches node ids out of arbitrary Cypher parameters and result rows.
NODE_ID = re.compile(r"^(?:ent|prog|per|loc|cat|art|clm)_[A-Za-z0-9_.:-]{1,64}$")
MAX_IDS = 200
MAX_ELEMENTS = 4000


def add_listener(fn: Listener) -> None:
    _listeners.add(fn)


def remove_listener(fn: Listener) -> None:
    _listeners.discard(fn)


async def _emit(event: str, payload: dict) -> None:
    for fn in list(_listeners):
        try:
            await fn(event, payload)
        except Exception:
            _listeners.discard(fn)


def node_ids(*objs: Any) -> list[str]:
    """Every graph node id reachable in the given params/rows, at any nesting depth."""
    found: dict[str, None] = {}

    def walk(v: Any) -> None:
        if isinstance(v, str):
            if NODE_ID.match(v):
                found[v] = None
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, (list, tuple, set)):
            for x in v:
                walk(x)

    for o in objs:
        walk(o)
    return list(found)


async def delta_for(ids: Iterable[str]) -> dict:
    """The named nodes and their immediate neighbourhood, in the shape the canvas draws."""
    wanted = list(dict.fromkeys(i for i in ids if i))[:MAX_IDS]
    if not wanted:
        return {"nodes": [], "edges": []}
    _, graph, _ = await db.read_graph(
        "MATCH (n) WHERE n.id IN $ids "
        "OPTIONAL MATCH (n)-[r]-(m) "
        "WITH collect(DISTINCT n) + collect(DISTINCT m) AS ns, collect(DISTINCT r) AS rs "
        "RETURN [x IN ns WHERE x IS NOT NULL][..$cap] AS nodes, rs[..$cap] AS rels",
        {"ids": wanted, "cap": MAX_ELEMENTS},
    )
    return subgraph_from_graph(graph)


async def announce(ids: Iterable[str], *, reason: str, source: str | None = None) -> None:
    """Broadcast what a write touched. Never raises: a notification must not be able
    to fail the write it is reporting."""
    if not _listeners:
        return
    try:
        focus = list(dict.fromkeys(i for i in ids if i))[:MAX_IDS]
        sub = await delta_for(focus)
        if not sub["nodes"]:
            return
        await _emit("graph_delta", {"subgraph": sub, "focus": focus, "reason": reason, "source": source})
    except Exception:
        return
