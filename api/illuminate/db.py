from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from collections.abc import Awaitable, Callable
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


async def probe(timeout: float = 3.0) -> dict[str, Any]:
    """Small, bounded database probe suitable for operator diagnostics."""
    try:
        started = asyncio.get_running_loop().time()
        rows = await asyncio.wait_for(
            read(
                "MATCH (n) WITH count(n) AS nodes "
                "OPTIONAL MATCH ()-[r]->() "
                "WITH nodes, count(r) AS relationships "
                "OPTIONAL MATCH (m) "
                "WHERE 'SeedMetadata' IN labels(m) AND m.id='primary' "
                "RETURN nodes, relationships, properties(m)['version'] AS seed_version, "
                "properties(m)['status'] AS seed_status, "
                "properties(m)['completed_at'] AS seed_completed_at, "
                "properties(m)['root_id'] AS seed_root_id, "
                "properties(m)['primes'] AS seed_primes, "
                "properties(m)['subs'] AS seed_subs",
                timeout=timeout,
            ),
            timeout=timeout,
        )
        row = rows[0] if rows else {}
        return {
            "status": "ready",
            "reachable": True,
            "counts": {
                "nodes": int(row.get("nodes", 0)),
                "relationships": int(row.get("relationships", 0)),
            },
            "seed_version": row.get("seed_version"),
            "seed_status": row.get("seed_status"),
            "seed_completed_at": row.get("seed_completed_at"),
            "seed_root_id": row.get("seed_root_id"),
            "seed_primes": int(row.get("seed_primes", 0) or 0),
            "seed_subs": int(row.get("seed_subs", 0) or 0),
            "latency_ms": round((asyncio.get_running_loop().time() - started) * 1000),
        }
    except (asyncio.TimeoutError, TimeoutError):
        return {"status": "unavailable", "reachable": False, "reason": "database probe timed out"}
    except Exception as exc:
        return {
            "status": "unavailable",
            "reachable": False,
            "reason": f"{type(exc).__name__}: database unavailable",
        }


async def seed_coverage(root_id: str, timeout: float = 3.0) -> dict[str, Any]:
    """Validate current mission paths rather than trusting historical seed counters."""
    try:
        rows = await asyncio.wait_for(
            read(
                "MATCH (root:Entity {id:$root_id}) "
                "OPTIONAL MATCH (prime:Entity)-[:SUPPLIES]->(root) "
                "OPTIONAL MATCH (sub:Entity)-[:SUPPLIES]->(:Entity)-[:SUPPLIES]->(root) "
                "RETURN count(DISTINCT root) > 0 AS root_exists, "
                "count(DISTINCT prime) AS primes, count(DISTINCT sub) AS subs",
                {"root_id": root_id},
                timeout=timeout,
            ),
            timeout=timeout,
        )
        row = rows[0] if rows else {}
        return {
            "status": "validated",
            "root_exists": bool(row.get("root_exists")),
            "primes": int(row.get("primes", 0) or 0),
            "subs": int(row.get("subs", 0) or 0),
        }
    except (asyncio.TimeoutError, TimeoutError):
        return {"status": "unknown", "root_exists": False, "primes": 0, "subs": 0,
                "reason": "seed coverage validation timed out"}
    except Exception as exc:
        return {"status": "unknown", "root_exists": False, "primes": 0, "subs": 0,
                "reason": f"{type(exc).__name__}: seed coverage unavailable"}


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


async def write(cypher: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
    """Committed write. Only the permission gate and trusted internals call this."""
    from neo4j import unit_of_work

    async with session(default_access_mode="WRITE") as s:

        @unit_of_work(timeout=timeout or settings.cypher_write_timeout_s)
        async def work(tx):
            res = await tx.run(cypher, params or {})
            rows = [r.data() for r in await res.fetch(settings.cypher_max_limit + 1)]
            summary = await res.consume()
            return {"rows": rows, "counters": counters_dict(summary.counters)}

        return await s.execute_write(work)


async def transactional_write(
    work: Callable[[Any], Awaitable[Any]],
    timeout: float | None = None,
) -> Any:
    """Run a multi-statement write as one retryable Neo4j transaction."""
    from neo4j import unit_of_work

    async with session(default_access_mode="WRITE") as s:

        @unit_of_work(timeout=timeout or settings.cypher_write_timeout_s)
        async def wrapped(tx):
            return await work(tx)

        return await s.execute_write(wrapped)


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
