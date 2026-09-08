"""Dedicated PostgreSQL connection for raw fetch-cache records.

The managed project database is isolated from the analytical Neo4j query
surface. Only the bearer-protected cache authority accesses these tables.
"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import asyncpg

_pool: asyncpg.Pool | None = None
_pool_loop: asyncio.AbstractEventLoop | None = None


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("managed fetch-cache database is not configured")
    return url


async def get_pool() -> asyncpg.Pool:
    global _pool, _pool_loop
    loop = asyncio.get_running_loop()
    if _pool is None or _pool_loop is not loop:
        if _pool is not None:
            await _pool.close()
        _pool = await asyncpg.create_pool(
            _database_url(),
            min_size=1,
            max_size=10,
            command_timeout=30,
        )
        _pool_loop = loop
    return _pool


async def close_driver() -> None:
    global _pool, _pool_loop
    if _pool is not None:
        await _pool.close()
    _pool = None
    _pool_loop = None


@asynccontextmanager
async def transaction() -> AsyncIterator[asyncpg.Connection]:
    pool = await get_pool()
    async with pool.acquire() as connection:
        async with connection.transaction():
            yield connection


async def fetchrow(query: str, *args: Any) -> asyncpg.Record | None:
    pool = await get_pool()
    return await pool.fetchrow(query, *args)


async def fetchval(query: str, *args: Any) -> Any:
    pool = await get_pool()
    return await pool.fetchval(query, *args)


async def execute(query: str, *args: Any) -> str:
    pool = await get_pool()
    return await pool.execute(query, *args)