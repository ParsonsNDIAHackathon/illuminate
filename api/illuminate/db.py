from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from .config import settings

_driver: AsyncDriver | None = None
_driver_loop: asyncio.AbstractEventLoop | None = None


async def get_driver() -> AsyncDriver:
    """One driver per event loop (tests and the MCP stdio entrypoint use their own)."""
    global _driver, _driver_loop
    loop = asyncio.get_running_loop()
    if _driver is None or _driver_loop is not loop:
        if _driver is not None:
            try:
                await _driver.close()
            except Exception:
                pass
        _driver = AsyncGraphDatabase.driver(settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password))
        _driver_loop = loop
    return _driver


async def close_driver() -> None:
    global _driver, _driver_loop
    if _driver is not None:
        try:
            await _driver.close()
        except Exception:
            pass
        _driver = None
        _driver_loop = None


@asynccontextmanager
async def session(**kw):
    driver = await get_driver()
    s = driver.session(database=settings.neo4j_database, **kw)
    try:
        yield s
    finally:
        await s.close()


async def read(cypher: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> list[dict]:
    """Read-only execution under a read transaction and a timeout."""
    from neo4j import unit_of_work

    async with session(default_access_mode="READ") as s:

        @unit_of_work(timeout=timeout or settings.cypher_read_timeout_s)
        async def work(tx):
            res = await tx.run(cypher, params or {})
            return [rec.data() for rec in await res.fetch(settings.cypher_max_limit + 1)]

        return await s.execute_read(work)


async def read_graph(cypher: str, params: dict[str, Any] | None = None, timeout: float | None = None):
    """Read returning both rows and the neo4j Graph object for subgraph extraction."""
    from neo4j import unit_of_work

    async with session(default_access_mode="READ") as s:

        @unit_of_work(timeout=timeout or settings.cypher_read_timeout_s)
        async def work(tx):
            res = await tx.run(cypher, params or {})
            records = await res.fetch(settings.cypher_max_limit + 1)
            graph = await res.graph()
            summary = await res.consume()
            return records, graph, summary

        return await s.execute_read(work)


async def write(cypher: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Committed write. Only the permission gate and trusted internals call this."""
    async with session(default_access_mode="WRITE") as s:

        async def work(tx):
            res = await tx.run(cypher, params or {})
            rows = [r.data() for r in await res.fetch(settings.cypher_max_limit + 1)]
            summary = await res.consume()
            return {"rows": rows, "counters": counters_dict(summary.counters)}

        return await s.execute_write(work)


async def dry_run(cypher: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute inside an explicit transaction and roll it back. The counters are
    from a real execution, not an estimate (D4)."""
    async with session(default_access_mode="WRITE") as s:
        tx = await s.begin_transaction()
        try:
            res = await tx.run(cypher, params or {})
            rows = [r.data() for r in await res.fetch(50)]
            summary = await res.consume()
            return {"rows": rows, "counters": counters_dict(summary.counters)}
        finally:
            await tx.rollback()


def counters_dict(c) -> dict[str, int]:
    keys = [
        "nodes_created", "nodes_deleted", "relationships_created", "relationships_deleted",
        "properties_set", "labels_added", "labels_removed", "indexes_added", "indexes_removed",
        "constraints_added", "constraints_removed",
    ]
    return {k: int(getattr(c, k, 0) or 0) for k in keys}
