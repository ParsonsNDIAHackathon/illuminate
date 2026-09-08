import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from illuminate.enrichment.worker import Job, Worker
from illuminate.connectors.base import Fact, NodeRef


class Connector:
    name = "test"
    trust = "authoritative"
    async def status(self, user):
        return {"connected": True}
    async def enrich(self, entity, user):
        raise RuntimeError("secret payload must not escape")


async def test_worker_failure_is_truthful_and_sanitized(monkeypatch):
    monkeypatch.setattr("illuminate.enrichment.worker.get_connector", lambda name: Connector())
    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    monkeypatch.setattr("illuminate.enrichment.worker.db.write", lambda *args, **kwargs: _result({}))
    monkeypatch.setattr(Worker, "_refresh_summary", _no_summary)
    w = Worker()
    job = Job("j", "e", "Entity", ["test"])
    await w.run(job)
    assert job.status == "failed"
    assert job.results["test"]["status"] == "failed"
    assert "secret payload" not in job.results["test"]["error"]
    assert job.results["test"]["attempts"] == 2


async def test_live_worker_rejects_simulated_connector_output_before_writing(monkeypatch):
    class SimulatedConnector:
        name = "simulated"
        trust = "authoritative"

        async def status(self, user):
            return {"connected": True}

        async def enrich(self, entity, user):
            return [
                Fact(
                    subject=NodeRef("Entity", "e", {"simulated": True}),
                    predicate="attr:uei",
                    value="not-production-evidence",
                )
            ]

    staged = False

    async def stage(*args, **kwargs):
        nonlocal staged
        staged = True

    monkeypatch.setattr("illuminate.enrichment.worker.get_connector", lambda name: SimulatedConnector())
    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    monkeypatch.setattr("illuminate.enrichment.worker.db.write", lambda *args, **kwargs: _result({}))
    monkeypatch.setattr("illuminate.enrichment.worker.claims.stage", stage)
    monkeypatch.setattr(Worker, "_refresh_summary", _no_summary)

    job = Job("j-simulated", "e", "Entity", ["simulated"], retrieval_mode="operational_live")
    await Worker().run(job)

    assert job.status == "failed"
    assert staged is False
    assert "simulated" not in job.results["simulated"]["error"]


async def _entity(*args, **kwargs):
    return [{"name": "Entity", "e": {"id": "e", "name": "Entity"}}]


async def _no_summary(self, job):
    job.summary_status = "unavailable"


async def test_database_probe_timeout_is_actionable(monkeypatch):
    from illuminate import db
    async def slow(*args, **kwargs):
        await asyncio.sleep(.1)
    monkeypatch.setattr(db, "read", slow)
    out = await db.probe(.001)
    assert out["status"] == "unavailable"
    assert "timed out" in out["reason"]


async def test_explicit_empty_connector_list_stays_empty(monkeypatch):
    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    w = Worker()
    monkeypatch.setattr(w, "start", lambda: None)
    job = await w.enqueue("e", connectors=[])
    assert job.connectors == []
    queued = await w.queue.get()
    await w.run(queued)
    assert job.status == "empty"
    assert job.to_dict()["terminal"] is True
    assert job.to_dict()["status_version"] == 2

async def test_enqueue_deduplicates_only_inside_bounded_refresh_window(monkeypatch):
    from illuminate.config import settings

    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    monkeypatch.setattr(settings, "enrichment_refresh_dedupe_window_s", 30)
    w = Worker()
    monkeypatch.setattr(w, "start", lambda: None)

    first = await w.enqueue("e", connectors=[])
    duplicate = await w.enqueue("e", connectors=[])
    assert duplicate is first
    assert w.queue.qsize() == 1

    first.created_at -= 31
    replacement = await w.enqueue("e", connectors=[])
    assert replacement.id != first.id
    assert w.queue.qsize() == 2
class FactsConnector:
    name = "facts"
    trust = "authoritative"
    async def status(self, user):
        return {"connected": True}
    async def enrich(self, entity, user):
        return [
            Fact(subject=NodeRef("Entity", "e"), predicate="attr:uei", value="ok"),
            Fact(subject=NodeRef("Entity", "e"), predicate="attr:cage", value="fails"),
        ]


async def test_partial_fact_writes_are_preserved_and_reported(monkeypatch):
    connector = FactsConnector()
    monkeypatch.setattr("illuminate.enrichment.worker.get_connector", lambda name: connector)
    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    monkeypatch.setattr(Worker, "_refresh_summary", _no_summary)
    calls = 0

    async def stage(fact, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("write failed")
        return "claim-1"

    monkeypatch.setattr("illuminate.enrichment.worker.claims.stage", stage)
    monkeypatch.setattr("illuminate.enrichment.worker.claims.decide", _committed)
    job = Job("j", "e", "Entity", ["facts"])
    await Worker().run(job)
    assert job.status == "partial"
    assert job.results["facts"]["status"] == "partial"
    assert job.results["facts"]["committed"] == 1
    assert job.results["facts"]["fact_errors"] == 1
    assert calls == 2


async def test_job_deadline_preserves_in_flight_write_counts(monkeypatch):
    from illuminate.config import settings

    connector = FactsConnector()
    monkeypatch.setattr("illuminate.enrichment.worker.get_connector", lambda name: connector)
    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    monkeypatch.setattr(settings, "enrichment_job_timeout_s", .02)
    calls = 0

    async def stage(fact, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            await asyncio.sleep(.2)
        return f"claim-{calls}"

    monkeypatch.setattr("illuminate.enrichment.worker.claims.stage", stage)
    monkeypatch.setattr("illuminate.enrichment.worker.claims.decide", _committed)
    job = Job("j", "e", "Entity", ["facts"])
    await Worker().run(job)
    assert job.status == "partial"
    assert job.results["facts"]["status"] == "partial"
    assert job.results["facts"]["committed"] == 1


class RecoveringConnector:
    name = "recovering"
    trust = "authoritative"
    calls = 0
    async def status(self, user):
        return {"connected": True}
    async def enrich(self, entity, user):
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("first attempt")
        return []


async def test_successful_retry_clears_active_failure(monkeypatch):
    connector = RecoveringConnector()
    monkeypatch.setattr("illuminate.enrichment.worker.get_connector", lambda name: connector)
    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    monkeypatch.setattr(Worker, "_refresh_summary", _no_summary)
    job = Job("j", "e", "Entity", ["recovering"])
    await Worker().run(job)
    result = job.results["recovering"]
    assert job.status == "empty"
    assert result["error"] is None
    assert result["action"].startswith("no new facts")
    assert result["recovered_after_attempts"] == 1


@pytest.mark.parametrize(
    ("model_output", "expected_status", "expected_fragment"),
    [
        ({"finding_ids": ["finding:risk:ownership"]}, "succeeded", "SET e.summary_finding_ids"),
        ({"finding_ids": ["not-approved"]}, "fallback", "REMOVE e.summary_finding_ids"),
    ],
)
async def test_summary_refresh_persists_only_validated_finding_selections(
    monkeypatch, model_output, expected_status, expected_fragment
):
    from illuminate.llm import client, tasks
    from illuminate import report

    rep = {
        "identity": {"id": "e", "name": "Entity", "simulated": False},
        "risk": {
            "categories": [{
                "id": "ownership",
                "severity": "high",
                "freshness": "current",
                "factors": [{
                    "truth_status": "committed",
                    "evidence_refs": ["clm_parent", "edge_parent"],
                    "explanation": "Validated foreign parent evidence.",
                }],
            }],
        },
    }
    writes = []

    async def fake_build_report(entity_id):
        return rep

    async def fake_json_call(user, system, user_msg, *, strong=False):
        return model_output

    async def fake_write(statement, params):
        writes.append((statement, params))

    monkeypatch.setattr(client, "has_key", lambda user: True)
    monkeypatch.setattr(report, "build_report", fake_build_report)
    monkeypatch.setattr(tasks, "_json_call", fake_json_call)
    monkeypatch.setattr(tasks, "models", lambda user: ("strong", "fast"))
    monkeypatch.setattr("illuminate.enrichment.worker.db.write", fake_write)

    job = Job("j-summary", "e", "Entity", [], user="local")
    await Worker()._refresh_summary(job)

    assert job.summary_status == expected_status
    assert job.summary_updated is (expected_status == "succeeded")
    assert len(writes) == 1
    assert expected_fragment in writes[0][0]
    if expected_status == "succeeded":
        assert writes[0][1]["f"] == ["finding:risk:ownership"]


async def test_summary_refresh_clears_stale_model_selection_without_key(monkeypatch):
    from illuminate.llm import client
    from illuminate import report

    rep = {
        "identity": {"id": "e", "name": "Entity", "simulated": False},
        "risk": {"categories": []},
    }
    writes = []

    async def fake_build_report(entity_id):
        return rep

    async def fake_write(statement, params):
        writes.append((statement, params))

    monkeypatch.setattr(client, "has_key", lambda user: False)
    monkeypatch.setattr(report, "build_report", fake_build_report)
    monkeypatch.setattr("illuminate.enrichment.worker.db.write", fake_write)

    job = Job("j-no-model", "e", "Entity", [], user="local")
    await Worker()._refresh_summary(job)

    assert job.summary_status == "unavailable"
    assert job.summary_updated is False
    assert len(writes) == 1
    assert "REMOVE e.summary_finding_ids" in writes[0][0]


@pytest.mark.parametrize("failure", ["timeout", "exception"])
async def test_summary_refresh_clears_stale_selection_on_failure(monkeypatch, failure):
    from illuminate.llm import client, tasks
    from illuminate import report
    from illuminate.config import settings

    writes = []

    async def fake_build_report(entity_id):
        return {
            "identity": {"id": "e", "name": "Entity", "simulated": False},
            "risk": {"categories": []},
        }

    async def failing_summary(user, rep):
        if failure == "timeout":
            await asyncio.sleep(0.05)
        raise RuntimeError("provider details")

    async def fake_write(statement, params):
        writes.append((statement, params))

    monkeypatch.setattr(client, "has_key", lambda user: True)
    monkeypatch.setattr(report, "build_report", fake_build_report)
    monkeypatch.setattr(tasks, "summarize_entity", failing_summary)
    monkeypatch.setattr("illuminate.enrichment.worker.db.write", fake_write)
    if failure == "timeout":
        monkeypatch.setattr(settings, "summary_timeout_s", 0.001)

    job = Job("j-failed-summary", "e", "Entity", [], user="local")
    await Worker()._refresh_summary(job)

    assert job.summary_status == ("timed_out" if failure == "timeout" else "failed")
    assert any("REMOVE e.summary_finding_ids" in statement for statement, _ in writes)
    assert "provider details" not in str(job.results)


async def test_outer_job_deadline_clears_in_flight_summary_selection(monkeypatch):
    from illuminate.config import settings

    writes = []

    async def slow_execute(self, job):
        job.summary_status = "running"
        await asyncio.sleep(0.05)

    async def fake_write(statement, params):
        writes.append((statement, params))

    monkeypatch.setattr(Worker, "_execute", slow_execute)
    monkeypatch.setattr("illuminate.enrichment.worker.db.write", fake_write)
    monkeypatch.setattr(settings, "enrichment_job_timeout_s", 0.001)

    job = Job("j-deadline-summary", "e", "Entity", [], user="local")
    await Worker().run(job)

    assert job.summary_status == "timed_out"
    assert any("REMOVE e.summary_finding_ids" in statement for statement, _ in writes)


async def test_recovered_retry_then_deadline_preserves_partial_result(monkeypatch):
    from illuminate.config import settings

    class RecoveringFacts(FactsConnector):
        calls = 0
        async def enrich(self, entity, user):
            self.calls += 1
            if self.calls == 1:
                raise TimeoutError("first attempt")
            return await super().enrich(entity, user)

    connector = RecoveringFacts()
    monkeypatch.setattr("illuminate.enrichment.worker.get_connector", lambda name: connector)
    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    monkeypatch.setattr("illuminate.enrichment.worker.asyncio.sleep", _no_wait)
    monkeypatch.setattr(settings, "enrichment_job_timeout_s", .02)
    calls = 0

    async def stage(fact, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            await _real_sleep(.2)
        return f"claim-{calls}"

    monkeypatch.setattr("illuminate.enrichment.worker.claims.stage", stage)
    monkeypatch.setattr("illuminate.enrichment.worker.claims.decide", _committed)
    job = Job("j", "e", "Entity", ["recovering"])
    await Worker().run(job)
    assert job.status == "partial"
    assert job.results["recovering"]["status"] == "partial"
    assert job.results["recovering"]["committed"] == 1
    assert job.results["recovering"]["attempts"] == 2


_real_sleep = asyncio.sleep


async def _no_wait(*args, **kwargs):
    return None


async def _committed(*args, **kwargs):
    return "committed"


async def test_readiness_requires_complete_seed_and_caches_per_user(monkeypatch):
    from illuminate import readiness

    class UserConnector:
        name = "openai"
        async def status(self, user):
            return {"connected": user == "alice", "needs_key": True}

    probe = {
        "status": "ready", "reachable": True, "counts": {"nodes": 20, "relationships": 10},
        "seed_version": "v1", "seed_status": "complete", "seed_root_id": "root",
        "seed_primes": 2, "seed_subs": 3, "seed_completed_at": "2026-09-08T00:00:00Z",
    }
    monkeypatch.setattr(readiness, "REGISTRY", [UserConnector()])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _result(probe))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _result({
        "status": "validated", "root_exists": True, "primes": 2, "subs": 3,
    }))
    monkeypatch.setattr(readiness.db, "read", _coverage)
    readiness._cache.clear()

    alice = await readiness.build_readiness("alice")
    bob = await readiness.build_readiness("bob")
    assert alice["primary_workflow_ready"] is True
    assert alice["optional_services"][0]["status"] == "connected"
    assert alice["optional_services"][0]["queried"] is True
    assert bob["optional_services"][0]["status"] == "credential-required"


async def _result(value):
    return value


async def _coverage(*args, **kwargs):
    return [{"source": "seed", "nodes": 20, "relationships": 10,
             "latest": datetime.now(timezone.utc).isoformat()}]


async def test_health_route_preserves_startup_contract_for_empty_graph(monkeypatch):
    payload = await _health_response(monkeypatch, {
        "status": "ready", "reachable": True, "counts": {"nodes": 0, "relationships": 0},
    })
    assert payload["ok"] is True
    assert payload["neo4j"] is True
    assert payload["primary_workflow_ready"] is False
    assert payload["status"] == "degraded"
    assert payload["version"]


async def test_health_route_reports_unavailable_database(monkeypatch):
    payload = await _health_response(monkeypatch, {
        "status": "unavailable", "reachable": False, "reason": "database unavailable",
    })
    assert payload["ok"] is False
    assert payload["neo4j"] is False
    assert payload["primary_workflow_ready"] is False
    assert payload["status"] == "unavailable"


async def test_health_route_reports_seeded_mission_readiness(monkeypatch):
    payload = await _health_response(monkeypatch, {
        "status": "ready", "reachable": True, "counts": {"nodes": 20, "relationships": 10},
        "seed_version": "v1", "seed_status": "complete", "seed_root_id": "root",
        "seed_primes": 2, "seed_subs": 3,
        "seed_completed_at": datetime.now(timezone.utc).isoformat(),
    }, seeded=True)
    assert payload["ok"] is True
    assert payload["primary_workflow_ready"] is True
    assert payload["required"]["seed"]["status"] == "ready"
    assert payload["status"] == "ready"

async def test_stale_sources_degrade_status_without_disabling_primary_workflow(monkeypatch):
    stale = {
        "status": "ready", "reachable": True, "counts": {"nodes": 20, "relationships": 10},
        "seed_version": "v1", "seed_status": "complete", "seed_root_id": "root",
        "seed_primes": 2, "seed_subs": 3,
        "seed_completed_at": datetime.now(timezone.utc).isoformat(),
    }

    async def stale_coverage(*args, **kwargs):
        return [{"source": "fixture", "nodes": 20, "relationships": 10,
                 "latest": "2020-01-01T00:00:00Z"}]

    from illuminate import readiness
    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _result(stale))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _result({
        "status": "validated", "root_exists": True, "primes": 2, "subs": 3,
    }))
    monkeypatch.setattr(readiness.db, "read", stale_coverage)
    readiness._cache.clear()

    payload = await readiness.build_readiness(refresh=True)
    assert payload["primary_workflow_ready"] is True
    assert payload["status"] == "degraded"
    assert payload["freshness"]["status"] == "stale"
    assert payload["freshness"]["action"]


async def test_readiness_ignores_error_and_fixture_ingestion_for_freshness(monkeypatch):
    from illuminate import readiness
    probe = {
        "status": "ready", "reachable": True, "counts": {"nodes": 3, "relationships": 1},
        "seed_version": "v1", "seed_status": "complete", "seed_root_id": "root",
        "seed_completed_at": datetime.now(timezone.utc).isoformat(),
    }
    seen = []

    async def evidence(query, *args, **kwargs):
        seen.append(query)
        # A cached record has no safe live-success timestamp.
        return [{"source": "gdelt", "nodes": 2, "relationships": 0, "latest": "",
                 "cached_records": 2}]

    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _result(probe))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _result(
        {"status": "validated", "root_exists": True, "primes": 1, "subs": 1}))
    monkeypatch.setattr(readiness.db, "read", evidence)
    readiness._cache.clear()
    payload = await readiness.build_readiness(refresh=True)
    source = payload["source_coverage"][0]
    assert source["status"] == "stale-fallback"
    assert source["last_success_at"] is None
    assert source["cache"] is True
    assert "NOT n:SourceRecord" in seen[0]
    assert "retrieval_mode" in seen[0]


async def test_readiness_never_treats_missing_retrieval_status_as_live(monkeypatch):
    from illuminate import readiness
    probe = {
        "status": "ready", "reachable": True, "counts": {"nodes": 1, "relationships": 0},
        "seed_version": "v1", "seed_status": "complete", "seed_root_id": "root",
        "seed_completed_at": datetime.now(timezone.utc).isoformat(),
    }

    async def unclassified(*args, **kwargs):
        return [{"source": "usaspending", "nodes": 1, "relationships": 0,
                 "latest": "", "cached_records": 0, "unknown_records": 1}]

    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _result(probe))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _result(
        {"status": "validated", "root_exists": True, "primes": 1, "subs": 1}))
    monkeypatch.setattr(readiness.db, "read", unclassified)
    readiness._cache.clear()
    payload = await readiness.build_readiness(refresh=True)
    source = payload["source_coverage"][0]
    assert source["status"] == "unknown"
    assert source["latest_retrieved_at"] is None
    assert source["unknown_records"] == 1


def test_production_entrypoint_uses_live_recovery_without_mandatory_fetch_cache():
    script = (Path(__file__).parents[2] / "scripts" / "replit-production.sh").read_text()
    assert "illuminate.seed.seed --bootstrap --skip-enrich" in script
    assert "--offline --scenario" not in script
    assert 'h.get("operational_refresh_required", True)' in script
    assert "ILLUMINATE_FETCH_CACHE_REQUIRED=true" not in script
    assert "Verifying managed fetch-cache schema" not in script
    assert "DATABASE_URL is required by the shared cache authority" not in script


def test_development_entrypoint_recovers_and_verifies_retained_credentials():
    script = (Path(__file__).parents[2] / "scripts" / "replit-dev.sh").read_text()
    recovery = script.index("write_neo4j_config false")
    rotate = script.index("ALTER USER neo4j SET PLAINTEXT PASSWORD")
    verify = script.index("driver.verify_connectivity()", rotate + 1)
    persist = script.index('mv "$PASSWORD_TMP" "$PASSWORD_FILE"')

    assert recovery < rotate < verify < persist
    assert "timeout --foreground" in script
    assert "Old password and new password cannot be the same" in script
    assert "wait_for_neo4j_http" in script
    assert "stop_process" in script
    assert "kill -KILL" in script
    assert "curl --max-time 2 -sf http://127.0.0.1:8000/api/health" in script
    assert "API readiness timed out" in script


async def test_operational_graph_without_seed_metadata_does_not_require_bootstrap(monkeypatch):
    from illuminate import readiness
    now = datetime.now(timezone.utc).isoformat()

    async def live_procurement(*args, **kwargs):
        query = args[0] if args else ""
        if ":SUPPLIES" in query:
            return [{"records": 3, "live_records": 3, "latest": now}]
        return [{"source": "usaspending", "nodes": 2, "relationships": 3,
                 "latest": now, "cached_records": 0, "unknown_records": 0}]

    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _result({
        "status": "ready", "reachable": True, "counts": {"nodes": 4, "relationships": 3},
    }))
    monkeypatch.setattr(readiness.db, "read", live_procurement)
    readiness._cache.clear()
    payload = await readiness.build_readiness(refresh=True)

    assert payload["primary_workflow_ready"] is False
    assert payload["operational_live_ready"] is True
    assert payload["operational_refresh_required"] is False
    assert payload["operational_coverage"]["live_supplier_paths"] == 3


async def test_fresh_award_evidence_without_supplier_path_requires_bootstrap(monkeypatch):
    from illuminate import readiness
    now = datetime.now(timezone.utc).isoformat()

    async def award_evidence_only(*args, **kwargs):
        query = args[0] if args else ""
        if ":SUPPLIES" in query:
            return [{"records": 0, "live_records": 0, "latest": ""}]
        return [{"source": "usaspending", "nodes": 1, "relationships": 2,
                 "latest": now, "cached_records": 0, "unknown_records": 0}]

    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _result({
        "status": "ready", "reachable": True, "counts": {"nodes": 3, "relationships": 2},
    }))
    monkeypatch.setattr(readiness.db, "read", award_evidence_only)
    readiness._cache.clear()
    payload = await readiness.build_readiness(refresh=True)

    assert payload["source_coverage"][0]["status"] == "current"
    assert payload["operational_live_ready"] is False
    assert payload["operational_refresh_required"] is True
    assert payload["operational_coverage"]["supplier_paths"] == 0


async def test_complete_offline_scenario_still_requires_operational_refresh(monkeypatch):
    from illuminate import readiness

    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _result({
        "status": "ready", "reachable": True, "counts": {"nodes": 20, "relationships": 10},
        "seed_version": "v1", "seed_status": "complete", "seed_root_id": "root",
        "seed_completed_at": datetime.now(timezone.utc).isoformat(),
        "seed_offline": True, "seed_scenario": True,
    }))
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _result({
        "status": "validated", "root_exists": True, "primes": 2, "subs": 3,
    }))
    monkeypatch.setattr(readiness.db, "read", _empty_coverage)
    readiness._cache.clear()
    payload = await readiness.build_readiness(refresh=True)

    assert payload["primary_workflow_ready"] is True
    assert payload["required"]["seed"]["offline"] is True
    assert payload["required"]["seed"]["scenario"] is True
    assert payload["operational_live_ready"] is False
    assert payload["operational_refresh_required"] is True
async def _health_response(monkeypatch, probe: dict, seeded: bool = False,
                           coverage: dict | None = None) -> dict:
    from illuminate import readiness
    from illuminate.main import app

    monkeypatch.setattr(readiness, "REGISTRY", [])
    monkeypatch.setattr(readiness.db, "probe", lambda *args: _result(probe))
    monkeypatch.setattr(readiness.db, "read", _coverage if seeded else _empty_coverage)
    monkeypatch.setattr(readiness.db, "seed_coverage", lambda *args: _result(coverage or {
        "status": "validated", "root_exists": True, "primes": 2, "subs": 3,
    }))
    readiness._cache.clear()
    assert len([r for r in app.routes if getattr(r, "path", None) == "/api/health"]) == 1
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/health?refresh=true")
    assert response.status_code == 200
    return response.json()


async def _empty_coverage(*args, **kwargs):
    return []

async def test_seed_verification_failure_is_explicit_even_with_populated_graph(monkeypatch):
    incomplete = {
        "status": "ready", "reachable": True, "counts": {"nodes": 20, "relationships": 10},
        "seed_version": "v1", "seed_status": "complete", "seed_root_id": "root",
        "seed_completed_at": datetime.now(timezone.utc).isoformat(),
    }
    payload = await _health_response(monkeypatch, incomplete, seeded=True, coverage={
        "status": "unavailable", "root_exists": False, "primes": 0, "subs": 0,
    })
    assert payload["ok"] is True
    assert payload["primary_workflow_ready"] is False
    assert payload["status"] == "degraded"
    assert payload["required"]["seed"]["status"] == "incomplete"
    assert payload["required"]["seed"]["coverage"]["status"] == "unavailable"
    assert payload["required"]["seed"]["action"]

async def test_failed_refresh_and_explicit_manual_retry_are_not_deduplicated(monkeypatch):
    monkeypatch.setattr("illuminate.enrichment.worker.db.read", _entity)
    w = Worker()
    monkeypatch.setattr(w, "start", lambda: None)

    failed = await w.enqueue("e", connectors=[])
    failed.status = "failed"
    automatic_retry = await w.enqueue("e", connectors=[])
    forced_retry = await w.enqueue("e", connectors=[], force=True)

    assert automatic_retry is not failed
    assert forced_retry is not automatic_retry
