"""Controlled development-only resilience matrix.

Required Neo4j failures must make readiness unavailable. Optional connector,
model, freshness, and catalog failures must remain explicit without corrupting
the deterministic path or duplicating remote writes.
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import SecretStr

from illuminate import readiness
from illuminate.config import settings
from illuminate.enrichment.worker import Job, Worker
from illuminate.routers import catalog


async def _value(value):
    return value


async def _fresh_sources(*args, **kwargs):
    return [{
        "source": "seed", "nodes": 10, "relationships": 5,
        "latest": datetime.now(timezone.utc).isoformat(),
    }]


def _seeded_probe():
    return {
        "status": "ready", "reachable": True,
        "counts": {"nodes": 10, "relationships": 5},
        "seed_version": "v1", "seed_status": "complete",
        "seed_root_id": "root", "seed_completed_at": "2026-09-08T00:00:00Z",
    }


async def test_required_database_outage_and_recovery_need_no_process_restart(monkeypatch):
    probes = iter([
        {"status": "unavailable", "reachable": False, "reason": "database unavailable"},
        _seeded_probe(),
    ])
    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _value(next(probes)))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _value({
        "status": "validated", "root_exists": True, "primes": 2, "subs": 3,
    }))
    monkeypatch.setattr(readiness.db, "read", _fresh_sources)
    readiness._cache.clear()

    failed = await readiness.build_readiness(refresh=True)
    recovered = await readiness.build_readiness(refresh=True)

    assert failed["ok"] is False
    assert failed["status"] == "unavailable"
    assert failed["primary_workflow_ready"] is False
    assert recovered["ok"] is True
    assert recovered["status"] == "ready"
    assert recovered["primary_workflow_ready"] is True


async def test_stale_cached_readiness_never_masks_refreshed_required_failure(monkeypatch):
    probes = iter([_seeded_probe(), {
        "status": "unavailable", "reachable": False, "reason": "database unavailable",
    }])
    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _value(next(probes)))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _value({
        "status": "validated", "root_exists": True, "primes": 2, "subs": 3,
    }))
    monkeypatch.setattr(readiness.db, "read", _fresh_sources)
    readiness._cache.clear()

    healthy = await readiness.build_readiness(refresh=True)
    cached = await readiness.build_readiness()
    failed = await readiness.build_readiness(refresh=True)

    assert healthy["status"] == "ready"
    assert cached["cached"] is True
    assert failed["status"] == "unavailable"
    assert failed["ok"] is False


async def test_optional_connector_timeout_preserves_deterministic_readiness(monkeypatch):
    class SlowConnector:
        name = "slow"

        async def status(self, user):
            await asyncio.sleep(.05)
            return {"connected": True}

    monkeypatch.setattr(readiness, "REGISTRY", [SlowConnector()])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _value(_seeded_probe()))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _value({
        "status": "validated", "root_exists": True, "primes": 2, "subs": 3,
    }))
    monkeypatch.setattr(readiness.db, "read", _fresh_sources)
    monkeypatch.setattr(settings, "readiness_timeout_s", .001)
    readiness._cache.clear()

    result = await readiness.build_readiness(refresh=True)

    assert result["primary_workflow_ready"] is True
    assert result["status"] == "ready"
    assert result["optional_services"][0]["status"] == "unavailable"


async def test_stale_source_data_is_degraded_but_deterministic_path_remains_ready(monkeypatch):
    stale = datetime.now(timezone.utc) - timedelta(hours=settings.freshness_stale_hours + 1)

    async def stale_sources(*args, **kwargs):
        return [{"source": "seed", "nodes": 10, "relationships": 5, "latest": stale.isoformat()}]

    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _value(_seeded_probe()))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _value({
        "status": "validated", "root_exists": True, "primes": 2, "subs": 3,
    }))
    monkeypatch.setattr(readiness.db, "read", stale_sources)
    readiness._cache.clear()

    result = await readiness.build_readiness(refresh=True)

    assert result["freshness"]["status"] == "stale"
    assert result["status"] == "degraded"
    assert result["primary_workflow_ready"] is True


async def test_cancelled_worker_loop_marks_job_failed_once(monkeypatch):
    worker = Worker()
    job = Job("job-one", "entity", "Entity", [])
    calls = 0

    async def cancelled_run(current):
        nonlocal calls
        calls += 1
        raise asyncio.CancelledError

    monkeypatch.setattr(worker, "run", cancelled_run)
    await worker.queue.put(job)
    task = asyncio.create_task(worker._loop())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls == 1
    await asyncio.wait_for(worker.queue.join(), timeout=.1)
    assert job.id == "job-one"


@pytest.fixture
def catalog_env(monkeypatch, tmp_path):
    monkeypatch.setattr(catalog.settings, "illuminate_data_dir", tmp_path)
    monkeypatch.setattr(catalog.settings, "illuminate_public_url", "https://illuminate.example")
    monkeypatch.setattr(catalog.settings, "ndia_key", SecretStr("server-only"))
    monkeypatch.setattr(catalog.settings, "ndia_catalog_operator_token", SecretStr("operator"))
    monkeypatch.setattr(catalog.settings, "ndia_catalog_contribution_path", "/contributions")
    monkeypatch.setattr(catalog.settings, "ndia_catalog_lookup_path", "/lookup")
    monkeypatch.setattr(catalog.settings, "ndia_catalog_status_path", "/status/{dataset_id}")
    monkeypatch.setattr(catalog.exports, "_sync_export_ledger", lambda: _value(7))


@pytest.mark.parametrize("unresolved_lookup", [{}, {"status": "pending_review"}])
async def test_malformed_portal_response_blocks_duplicate_post_and_recovers_by_lookup(
    catalog_env, monkeypatch, unresolved_lookup,
):
    calls = []

    async def portal_request(method, path, *, body=None, idempotency_key=None):
        calls.append(method)
        if method == "POST":
            return {"status": "accepted"}  # malformed: no stable remote identity
        lookup = calls.count("GET")
        if lookup == 1:
            return {}
        if lookup == 2:
            return unresolved_lookup
        return {"dataset_id": "ds-recovered", "status": "pending_review"}

    monkeypatch.setattr(catalog, "_portal_request", portal_request)
    preview = await catalog._preview("local")
    request = catalog.SubmitRequest(
        confirm=True, confirmation="PUBLISH EVENT 3",
        confirmation_token=preview.confirmation_token, dry_run=False,
    )

    with pytest.raises(catalog.HTTPException) as malformed:
        await catalog.submit(request, "local", "operator")
    assert malformed.value.status_code == 502

    with pytest.raises(catalog.HTTPException) as blocked:
        await catalog.submit(request, "local", "operator")
    assert blocked.value.status_code == 409
    assert calls.count("POST") == 1

    recovered = await catalog.status(refresh=True)
    repeated = await catalog.submit(request, "local", "operator")
    assert recovered.dataset_id == "ds-recovered"
    assert repeated.dataset_id == "ds-recovered"
    assert repeated.idempotent is True
    assert calls.count("POST") == 1