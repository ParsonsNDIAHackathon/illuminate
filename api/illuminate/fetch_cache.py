"""Durable, immutable fetch-once cache coordination."""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from . import fetch_cache_db as db

_schema_ready = False
_schema_lock = asyncio.Lock()


async def ensure_schema() -> None:
    """Fail closed until publish-managed cache tables are available."""
    global _schema_ready
    if _schema_ready:
        return
    async with _schema_lock:
        if _schema_ready:
            return
        ready = await db.fetchval(
            "SELECT to_regclass('public.fetch_cache_schema') IS NOT NULL "
            "AND to_regclass('public.fetch_cache_records') IS NOT NULL "
            "AND to_regclass('public.fetch_cache_leases') IS NOT NULL "
            "AND to_regclass('public.fetch_cache_guards') IS NOT NULL "
            "AND EXISTS(SELECT 1 FROM fetch_cache_schema WHERE version=1) "
            "AND (SELECT count(*) FROM pg_constraint WHERE contype='p' AND conrelid IN ("
            "'fetch_cache_records'::regclass, 'fetch_cache_leases'::regclass, "
            "'fetch_cache_guards'::regclass))=3"
        )
        if not ready:
            raise RuntimeError("fetch-cache database schema is not ready")
        _schema_ready = True


def schema_ready() -> bool:
    return _schema_ready


def _decode_record(value: Any) -> dict[str, Any]:
    return json.loads(value) if isinstance(value, str) else dict(value)


def _authoritative_record(
    value: Any, namespace: str, identity: str,
) -> dict[str, Any]:
    return {
        **_decode_record(value),
        "namespace": namespace,
        "identity": identity,
    }


async def get_record(namespace: str, identity: str) -> dict[str, Any] | None:
    row = await db.fetchrow(
        "SELECT record FROM fetch_cache_records "
        "WHERE namespace=$1 AND identity=$2",
        namespace,
        identity,
    )
    return _authoritative_record(row["record"], namespace, identity) if row else None


async def _lock_guard(connection, namespace: str, identity: str) -> None:
    await connection.execute(
        "INSERT INTO fetch_cache_guards(namespace, identity, lock_version) "
        "VALUES($1, $2, 0) ON CONFLICT(namespace, identity) DO NOTHING",
        namespace,
        identity,
    )
    await connection.fetchrow(
        "UPDATE fetch_cache_guards SET lock_version=lock_version + 1 "
        "WHERE namespace=$1 AND identity=$2 RETURNING lock_version",
        namespace,
        identity,
    )


async def claim(namespace: str, identity: str, lease_s: float) -> dict[str, Any]:
    now = time.time()
    owner = uuid.uuid4().hex
    async with db.transaction() as connection:
        await _lock_guard(connection, namespace, identity)
        existing = await connection.fetchrow(
            "SELECT record FROM fetch_cache_records "
            "WHERE namespace=$1 AND identity=$2",
            namespace,
            identity,
        )
        if existing:
            return {
                "state": "complete",
                "record": _authoritative_record(
                    existing["record"], namespace, identity,
                ),
            }
        await connection.execute(
            "INSERT INTO fetch_cache_leases("
            "namespace, identity, owner, fence, lease_until, created_at, updated_at"
            ") VALUES($1, $2, '', 0, 0, $3, $3) "
            "ON CONFLICT(namespace, identity) DO NOTHING",
            namespace,
            identity,
            now,
        )
        lease = await connection.fetchrow(
            "SELECT owner, fence, lease_until FROM fetch_cache_leases "
            "WHERE namespace=$1 AND identity=$2 FOR UPDATE",
            namespace,
            identity,
        )
        acquired = float(lease["lease_until"]) < now
        if acquired:
            lease = await connection.fetchrow(
                "UPDATE fetch_cache_leases "
                "SET owner=$3, fence=fence + 1, lease_until=$4, updated_at=$5 "
                "WHERE namespace=$1 AND identity=$2 "
                "RETURNING owner, fence, lease_until",
                namespace,
                identity,
                owner,
                now + max(1.0, lease_s),
                now,
            )
        return {
            "state": "claimed" if acquired else "waiting",
            "owner": owner if acquired else None,
            "fence": int(lease["fence"]) if acquired else None,
            "lease_until": float(lease["lease_until"]),
        }


async def renew(
    namespace: str, identity: str, owner: str, fence: int, lease_s: float,
) -> float:
    now = time.time()
    row = await db.fetchrow(
        "UPDATE fetch_cache_leases SET lease_until=$6, updated_at=$5 "
        "WHERE namespace=$1 AND identity=$2 AND owner=$3 AND fence=$4 "
        "AND lease_until >= $5 RETURNING lease_until",
        namespace,
        identity,
        owner,
        fence,
        now,
        now + max(1.0, lease_s),
    )
    if not row:
        raise PermissionError("cache lease was lost")
    return float(row["lease_until"])


async def publish(
    namespace: str,
    identity: str,
    owner: str,
    fence: int,
    record: dict[str, Any],
) -> dict[str, Any]:
    record = {**record, "first_retrieved_at": time.time()}
    async with db.transaction() as connection:
        await _lock_guard(connection, namespace, identity)
        lease = await connection.fetchrow(
            "SELECT lease_until FROM fetch_cache_leases "
            "WHERE namespace=$1 AND identity=$2 AND owner=$3 AND fence=$4 FOR UPDATE",
            namespace,
            identity,
            owner,
            fence,
        )
        if not lease or float(lease["lease_until"]) < time.time():
            raise PermissionError("cache lease was lost")
        await connection.execute(
            "INSERT INTO fetch_cache_records(namespace, identity, record, created_at) "
            "VALUES($1, $2, $3::jsonb, $4) "
            "ON CONFLICT(namespace, identity) DO NOTHING",
            namespace,
            identity,
            json.dumps(record, separators=(",", ":")),
            record["first_retrieved_at"],
        )
        authoritative = await connection.fetchrow(
            "SELECT record FROM fetch_cache_records "
            "WHERE namespace=$1 AND identity=$2",
            namespace,
            identity,
        )
        await connection.execute(
            "DELETE FROM fetch_cache_leases "
            "WHERE namespace=$1 AND identity=$2 AND owner=$3 AND fence=$4",
            namespace,
            identity,
            owner,
            fence,
        )
        return _authoritative_record(
            authoritative["record"], namespace, identity,
        )


async def release(
    namespace: str,
    identity: str,
    owner: str,
    fence: int,
    *,
    retry_after_s: float,
) -> None:
    now = time.time()
    await db.execute(
        "UPDATE fetch_cache_leases "
        "SET owner='cooldown', lease_until=$5, updated_at=$6 "
        "WHERE namespace=$1 AND identity=$2 AND owner=$3 AND fence=$4",
        namespace,
        identity,
        owner,
        fence,
        now + max(1.0, retry_after_s),
        now,
    )