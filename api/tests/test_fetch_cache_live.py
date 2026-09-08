"""Fetch-cache contention against the managed PostgreSQL database."""
import asyncio
import base64
import hashlib
import multiprocessing
import time
import uuid

import pytest
import httpx
from fastapi import FastAPI
from pydantic import SecretStr

from illuminate import fetch_cache, fetch_cache_db
from illuminate.config import settings
from illuminate.connectors import http
from illuminate.routers import fetch_cache as fetch_cache_router


def _claim_in_process(namespace, identity, start, queue):
    async def run():
        start.wait(10)
        try:
            queue.put(await fetch_cache.claim(namespace, identity, 5))
        except Exception as exc:
            queue.put({"error": type(exc).__name__})
        finally:
            await fetch_cache_db.close_driver()

    asyncio.run(run())


async def _reachable():
    await fetch_cache_db.close_driver()
    try:
        return await fetch_cache_db.fetchval("SELECT 1") == 1
    except Exception:
        return False


async def test_live_postgres_coordinates_processes_and_fences_stale_publishers():
    if not await _reachable():
        pytest.skip("managed PostgreSQL is not reachable")
    await fetch_cache.ensure_schema()
    namespace = "test-" + uuid.uuid4().hex
    identity = hashlib.sha256(namespace.encode()).hexdigest()
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    queue = context.Queue()
    processes = [
        context.Process(target=_claim_in_process, args=(namespace, identity, start, queue))
        for _ in range(4)
    ]
    try:
        for process in processes:
            process.start()
        start.set()
        for process in processes:
            process.join(15)
            assert process.exitcode == 0
        claims = [queue.get(timeout=2) for _ in processes]
        assert not [claim for claim in claims if "error" in claim]
        winners = [claim for claim in claims if claim["state"] == "claimed"]
        assert len(winners) == 1
        assert len([claim for claim in claims if claim["state"] == "waiting"]) == 3

        winner = winners[0]
        payload = b'{"from":"first-writer"}'
        record = await fetch_cache.publish(
            namespace,
            identity,
            winner["owner"],
            winner["fence"],
            {
                "source": "live-test",
                "request": '{"body":null,"contract":"test-v1","credential_scope":null,'
                           '"method":"GET","representation":"json","source":"live-test",'
                           '"url":"https://example.test/data"}',
                "final_url": "https://example.test/data",
                "content_type": "application/json",
                "truncated": False,
                "content_hash": hashlib.sha256(payload).hexdigest(),
                "payload_b64": base64.b64encode(payload).decode(),
            },
        )
        assert record["first_retrieved_at"] <= time.time()
        hit = await fetch_cache.claim(namespace, identity, 5)
        assert hit["state"] == "complete"
        assert hit["record"]["payload_b64"] == record["payload_b64"]
        # Closing the process-local pool simulates a process/deployment restart;
        # the immutable record remains authoritative in managed PostgreSQL.
        await fetch_cache_db.close_driver()
        restarted_hit = await fetch_cache.claim(namespace, identity, 5)
        assert restarted_hit["state"] == "complete"
        assert restarted_hit["record"] == hit["record"]
        with pytest.raises(PermissionError):
            await fetch_cache.publish(
                namespace,
                identity,
                winner["owner"],
                winner["fence"],
                {**record, "payload_b64": base64.b64encode(b"changed").decode()},
            )
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(timeout=2)
        await fetch_cache_db.execute(
            "DELETE FROM fetch_cache_records WHERE namespace=$1", namespace,
        )
        await fetch_cache_db.execute(
            "DELETE FROM fetch_cache_leases WHERE namespace=$1", namespace,
        )
        await fetch_cache_db.execute(
            "DELETE FROM fetch_cache_guards WHERE namespace=$1", namespace,
        )
        await fetch_cache_db.close_driver()


async def test_connector_reuses_real_authority_after_storage_reopens(monkeypatch):
    if not await _reachable():
        pytest.skip("managed PostgreSQL is not reachable")
    await fetch_cache.ensure_schema()
    namespace = "test-" + uuid.uuid4().hex
    monkeypatch.setattr(settings, "illuminate_fetch_cache_namespace", namespace)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", "http://cache.test")
    monkeypatch.setattr(settings, "illuminate_fetch_cache_required", True)
    monkeypatch.setattr(settings, "illuminate_fetch_cache_authority_enabled", True)
    monkeypatch.setattr(
        settings, "illuminate_fetch_cache_token", SecretStr("test-cache-token"),
    )
    service = FastAPI()
    service.include_router(fetch_cache_router.router)
    real_client = httpx.AsyncClient

    def authority_client(**kwargs):
        return real_client(
            transport=httpx.ASGITransport(app=service),
            base_url="http://cache.test",
            **kwargs,
        )

    monkeypatch.setattr(http.httpx, "AsyncClient", authority_client)
    identity, identity_doc = http.canonical_request_identity(
        "live-service-test",
        "GET",
        "https://example.test/data",
        None,
        "json",
        contract="test-v1",
    )
    upstream_calls = 0

    async def producer():
        nonlocal upstream_calls
        upstream_calls += 1
        return {
            "payload": b'{"from":"upstream"}',
            "final_url": "https://example.test/data",
            "content_type": "application/json",
            "truncated": False,
        }

    try:
        first, first_hit = await http._shared_fetch(identity, identity_doc, producer)
        assert first_hit is False
        assert first["namespace"] == namespace
        assert first["identity"] == identity
        assert first["payload"] == b'{"from":"upstream"}'

        await fetch_cache_db.close_driver()
        second, second_hit = await http._shared_fetch(identity, identity_doc, producer)
        assert second_hit is True
        assert second["namespace"] == namespace
        assert second["identity"] == identity
        assert second["payload"] == first["payload"]
        assert upstream_calls == 1
    finally:
        await fetch_cache_db.execute(
            "DELETE FROM fetch_cache_records WHERE namespace=$1", namespace,
        )
        await fetch_cache_db.execute(
            "DELETE FROM fetch_cache_leases WHERE namespace=$1", namespace,
        )
        await fetch_cache_db.execute(
            "DELETE FROM fetch_cache_guards WHERE namespace=$1", namespace,
        )
        await fetch_cache_db.close_driver()