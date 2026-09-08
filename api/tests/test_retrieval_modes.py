import json
import time

import httpx

from illuminate.connectors import http
from illuminate.config import settings
from illuminate.enrichment.sources import select_connectors
from illuminate.enrichment.worker import Job, Worker
from illuminate.enrichment import claims
from illuminate.connectors.base import Fact, NodeRef, ArtifactRef


class _Client:
    def __init__(self, response=None, error=None, **kwargs):
        self.response = response
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def request(self, *args, **kwargs):
        if self.error:
            raise self.error
        return self.response


async def test_operational_live_never_reads_fixture_store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "illuminate_fetch_cache_required", False)
    url = "https://example.test/value"
    http.set_cache_dir(tmp_path, read_only=True, fixture_store=True)
    path = tmp_path / f"{http._key('GET', url, None)}.json"
    path.write_text(json.dumps({"_ts": time.time(), "body": {"origin": "fixture"}}))
    response = httpx.Response(200, json={"origin": "live"}, request=httpx.Request("GET", url))
    monkeypatch.setattr(http.httpx, "AsyncClient", lambda **kwargs: _Client(response=response))

    with http.retrieval_context("operational_live") as trace:
        result = await http.fetch_json("GET", url)

    assert result == {"origin": "live"}
    assert trace[-1]["source_status"] == "live"


async def test_offline_fixture_is_explicit_and_reported(tmp_path):
    url = "https://example.test/value"
    http.set_cache_dir(tmp_path, read_only=True, fixture_store=True)
    path = tmp_path / f"{http._key('GET', url, None)}.json"
    path.write_text(json.dumps({"_ts": 1, "body": {"origin": "fixture"}}))

    with http.retrieval_context("offline_fixture") as trace:
        result = await http.fetch_json("GET", url)

    assert result == {"origin": "fixture"}
    assert trace[-1]["source_status"] == "offline_fixture"


async def test_explicit_recording_exports_shared_json_hit_to_fixture_store(
    tmp_path, monkeypatch,
):
    url = "https://example.test/value"
    payload = b'{"origin":"shared"}'

    async def shared_fetch(_identity, _document, _producer):
        return {
            "payload": payload,
            "first_retrieved_at": 1_700_000_000.0,
            "final_url": url,
            "content_type": "application/json",
            "truncated": False,
        }, True

    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", "https://cache.test")
    monkeypatch.setattr(http, "_shared_fetch", shared_fetch)
    http.set_cache_dir(
        tmp_path, read_only=False, fixture_store=True, recording=True,
    )
    try:
        result = await http.fetch_json("GET", url)
        path = tmp_path / f"{http._key('GET', url, None)}.json"
        fixture = json.loads(path.read_text())
    finally:
        http.set_cache_dir(None)

    assert result == {"origin": "shared"}
    assert fixture == {
        "_ts": 1_700_000_000.0,
        "url": url,
        "body": {"origin": "shared"},
    }


async def test_explicit_recording_reuses_existing_fixtures_without_shared_calls(
    tmp_path, monkeypatch,
):
    json_url = "https://example.test/value"
    text_url = "https://example.test/page"
    document_url = "https://93.184.216.34/document"
    json_path = tmp_path / f"{http._key('GET', json_url, None)}.json"
    text_path = tmp_path / f"{http._key('GET', text_url, None)}.txt"
    document_path = tmp_path / f"{http._key('GET', document_url, None)}.doc"
    document_meta = tmp_path / f"{http._key('GET', document_url, None)}.doc.json"
    json_fixture = json.dumps({
        "_ts": 1,
        "url": json_url,
        "body": {"origin": "existing"},
    })
    document_fixture = b"existing document"
    document_metadata = json.dumps({
        "_ts": 1,
        "url": document_url,
        "content_type": "application/octet-stream",
        "truncated": False,
    })
    json_path.write_text(json_fixture)
    text_path.write_text("existing text")
    document_path.write_bytes(document_fixture)
    document_meta.write_text(document_metadata)

    async def unexpected_shared_call(*_args, **_kwargs):
        raise AssertionError("existing recording fixture must not contact shared cache")

    monkeypatch.setattr(settings, "illuminate_fetch_cache_url", "https://cache.test")
    monkeypatch.setattr(http, "_shared_fetch", unexpected_shared_call)
    http.set_cache_dir(
        tmp_path, read_only=False, fixture_store=True, recording=True,
    )
    try:
        json_result = await http.fetch_json("GET", json_url)
        text_result = await http.fetch_text(text_url)
        document_result = await http.fetch_document(document_url)
    finally:
        http.set_cache_dir(None)

    assert json_result == {"origin": "existing"}
    assert text_result == "existing text"
    assert document_result["body"] == document_fixture
    assert json_path.read_text() == json_fixture
    assert text_path.read_text() == "existing text"
    assert document_path.read_bytes() == document_fixture
    assert document_meta.read_text() == document_metadata


async def test_bounded_stale_fallback_is_visible(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "illuminate_fetch_cache_required", False)
    url = "https://example.test/value"
    http.set_cache_dir(tmp_path)
    path = tmp_path / f"{http._key('GET', url, None)}.json"
    path.write_text(json.dumps({"_ts": time.time() - 20, "body": {"origin": "cache"}}))
    monkeypatch.setattr(http.httpx, "AsyncClient",
                        lambda **kwargs: _Client(error=httpx.ConnectError("down")))

    with http.retrieval_context("operational_live") as trace:
        result = await http.fetch_json("GET", url, ttl=1)

    assert result == {"origin": "cache"}
    assert trace[-1]["source_status"] == "stale_fallback"
    assert trace[-1]["cache_age_s"] >= 20
    assert trace[-1]["retrieved_at"]


def test_worker_preserves_oldest_backing_retrieval_timestamp():
    result = {}
    Worker._apply_retrieval_result(result, [
        {
            "source_status": "live",
            "cache_age_s": 0,
            "retrieved_at": "2026-09-08T12:00:00Z",
        },
        {
            "source_status": "cached",
            "cache_age_s": 20 * 86400,
            "retrieved_at": "2026-08-19T12:00:00Z",
        },
    ])

    assert result["retrieved_at"] == "2026-08-19T12:00:00Z"
    assert result["cache_age_s"] == 20 * 86400
    assert result["cache"] is True


async def test_worker_carries_retrieval_timestamp_into_fact_and_artifact(monkeypatch):
    observed = []
    fact = Fact(
        NodeRef("Entity", "supplier"),
        "sanctions_screen",
        value="clear",
        artifact=ArtifactRef("https://example.test/screen", "Screen"),
    )

    async def stage(value, **kwargs):
        observed.append(value)
        return "claim"

    async def decide(*args, **kwargs):
        return "committed"

    monkeypatch.setattr(claims, "stage", stage)
    monkeypatch.setattr(claims, "decide", decide)
    result = {
        "retrieval_mode": "operational_live",
        "source_status": "stale_fallback",
        "retrieved_at": "2026-08-19T12:00:00Z",
        "cache_age_s": 20 * 86400,
        "cache": True,
        "fallback": True,
        "staged": 0,
        "committed": 0,
    }
    connector = type("Connector", (), {"name": "ofac", "trust": "authoritative"})()

    await Worker()._process_facts(connector, [fact], result, {})

    assert observed[0].props["retrieved_at"] == "2026-08-19T12:00:00Z"
    assert observed[0].artifact.props["retrieved_at"] == "2026-08-19T12:00:00Z"
    assert observed[0].props["cache"] is True
    assert observed[0].artifact.props["fallback"] is True


async def test_bootstrap_merges_preserve_cached_http_truth(monkeypatch):
    from illuminate.seed import seed

    writes = []
    original_mode, original_trace = seed._seed_retrieval_mode, seed._seed_retrieval_trace

    async def write(query, params=None):
        writes.append((query, params))

    monkeypatch.setattr(seed.db, "write", write)
    seed._seed_retrieval_mode = "operational_live"
    seed._seed_retrieval_trace = [{
        "source_status": "cached", "cache_age_s": 3600,
        "retrieved_at": "2026-09-08T10:00:00Z",
    }]
    try:
        await seed.merge_entity("ent_cached", {"name": "Cached supplier", "source": "USAspending"})
        await seed.merge_rel("ent_cached", "SUPPLIES", "program", {"source": "USAspending"})
    finally:
        seed._seed_retrieval_mode, seed._seed_retrieval_trace = original_mode, original_trace

    for _, params in writes:
        assert params["p"]["source_status"] == "cached"
        assert params["p"]["cache_age_s"] == 3600
        # merge helpers intentionally retain the actual response timestamp,
        # rather than generating an ingestion-time substitute.
        assert params["retrieved"] == "2026-09-08T10:00:00Z"


async def test_bootstrap_aggregate_cannot_borrow_later_live_timestamp(monkeypatch):
    from illuminate.seed import seed

    supplies = []
    original_mode, original_trace = seed._seed_retrieval_mode, seed._seed_retrieval_trace
    seed._seed_retrieval_mode = "operational_live"
    seed._seed_retrieval_trace = []

    async def search_awards(*args, **kwargs):
        seed._seed_retrieval_trace.append({
            "source_status": "stale_fallback",
            "cache_age_s": 20 * 86400,
            "retrieved_at": "2026-08-19T12:00:00Z",
        })
        return {
            "results": [{
                "recipient_id": "recipient-1",
                "Recipient Name": "Cached Prime",
                "Award Amount": 100,
                "Award ID": "award-1",
                "generated_internal_id": "generated-award-1",
                "Description": "Cached search result",
            }],
            "page_metadata": {"hasNext": False},
        }

    async def recipient(*args, **kwargs):
        seed._seed_retrieval_trace.append({
            "source_status": "live",
            "cache_age_s": 0,
            "retrieved_at": "2026-09-08T12:00:00Z",
        })
        return {"uei": "TESTUEI", "name": "Cached Prime"}

    async def award_detail(*args, **kwargs):
        seed._seed_retrieval_trace.append({
            "source_status": "live",
            "cache_age_s": 0,
            "retrieved_at": "2026-09-08T12:01:00Z",
        })
        return {"latest_transaction_contract_data": {"product_or_service_code": "1510"}}

    async def merge_entity(*args, **kwargs):
        return None

    async def merge_rel(src, rel, dst, props, key_props=None, *, retrievals=None):
        if rel == "SUPPLIES":
            supplies.append(seed._with_retrieval_truth(props, retrievals))

    async def merge_artifact(*args, **kwargs):
        return None

    monkeypatch.setattr(seed, "search_awards", search_awards)
    monkeypatch.setattr(seed, "recipient", recipient)
    monkeypatch.setattr(seed, "award_detail", award_detail)
    monkeypatch.setattr(seed, "merge_entity", merge_entity)
    monkeypatch.setattr(seed, "merge_rel", merge_rel)
    monkeypatch.setattr(seed, "merge_artifact", merge_artifact)
    try:
        await seed.seed_program(
            ["test"],
            "Timestamp Program",
            since="2026-01-01",
            until="2026-09-08",
            max_primes=1,
            max_subs=0,
            agency="",
        )
    finally:
        seed._seed_retrieval_mode, seed._seed_retrieval_trace = original_mode, original_trace

    supplier_edge = next(item for item in supplies if item.get("tier") == 1)
    assert supplier_edge["source_status"] == "stale_fallback"
    assert supplier_edge["retrieval_status"] == "stale_fallback"
    assert supplier_edge["retrieved_at"] == "2026-08-19T12:00:00Z"
    assert supplier_edge["cache_age_s"] == 20 * 86400
    assert supplier_edge["cache"] is True
    assert supplier_edge["fallback"] is True


def test_automatic_source_selection_is_contextual_and_resume_safe():
    class Source:
        def __init__(self, name, kinds):
            self.name, self.kinds = name, kinds

        def applies_to(self, entity):
            return entity["kind"] in self.kinds

    sources = [Source("company", ("organization",)), Source("awards", ("program",)), Source("openai", ("program",))]
    assert select_connectors({"kind": "program"}, sources) == ["awards"]
    assert select_connectors(
        {"kind": "program"}, sources, requested=["missing", "awards"],
        previous_results={"awards": {"status": "succeeded"}},
    ) == ["missing"]


def test_observation_key_is_stable_for_rerun_and_changes_with_upstream_record():
    fact = Fact(NodeRef("Entity", "subject"), "attr:cik", value="100",
                artifact=ArtifactRef("https://source.test/filing/1", "Filing"))
    assert claims.observation_key(fact, "edgar") == claims.observation_key(fact, "edgar")
    changed = Fact(NodeRef("Entity", "subject"), "attr:cik", value="100",
                   artifact=ArtifactRef("https://source.test/filing/2", "Filing"))
    assert claims.observation_key(fact, "edgar") != claims.observation_key(changed, "edgar")


def test_observation_key_and_artifact_identity_distinguish_dated_source_records():
    first = Fact(
        NodeRef("Entity", "subject"), "vulnerability_screen", value="0.5",
        artifact=ArtifactRef(
            "https://api.first.org/data/v1/epss?cve=CVE-2021-44228",
            "EPSS",
            props={"source_identifier": "CVE-2021-44228:2026-09-08"},
        ),
    )
    second = Fact(
        NodeRef("Entity", "subject"), "vulnerability_screen", value="0.5",
        artifact=ArtifactRef(
            "https://api.first.org/data/v1/epss?cve=CVE-2021-44228",
            "EPSS",
            props={"source_identifier": "CVE-2021-44228:2026-09-09"},
        ),
    )
    assert claims.observation_key(first, "epss") != claims.observation_key(second, "epss")


async def test_resume_uses_durable_checkpoint_when_worker_memory_is_empty(monkeypatch):
    from illuminate.enrichment import checkpoints
    superseded = []

    async def entity(*args, **kwargs):
        return [{"e": {"id": "entity", "name": "Entity", "kind": "organization"}}]

    async def stored(job_id):
        return {"id": job_id, "entity_id": "entity", "connectors": ["one", "two"],
                "results": {"one": {"status": "succeeded"}, "two": {"status": "partial"}}}

    monkeypatch.setattr("illuminate.enrichment.worker.db.read", entity)
    monkeypatch.setattr(checkpoints, "load", stored)
    monkeypatch.setattr(checkpoints, "save", lambda job: _async_none())
    monkeypatch.setattr(
        checkpoints,
        "mark_superseded",
        lambda old, new: _record_async(superseded, (old, new)),
    )
    monkeypatch.setattr("illuminate.enrichment.worker.REGISTRY", [])
    worker = Worker()
    monkeypatch.setattr(worker, "start", lambda: None)
    job = await worker.enqueue("entity", connectors=None, resume_job_id="prior")
    assert job.resumed_from == "prior"
    assert job.connectors == ["two"]
    assert superseded == [("prior", job.id)]


async def test_program_procurement_queues_bounded_durable_supplier_children(monkeypatch):
    from illuminate.enrichment import checkpoints

    worker = Worker()
    parent = Job("parent", "program", "Program", ["usaspending"])
    queued = []

    async def suppliers(query, params=None):
        assert params["limit"] > 0
        assert "EnrichmentJob" not in query, "persisted abandoned states must not suppress replacement jobs"
        return [{"id": "supplier-1"}, {"id": "supplier-2"}]

    async def enqueue(entity_id, connectors=None, user="local", requested_by="ui",
                      retrieval_mode="operational_live", resume_job_id=None, parent_job_id=None):
        queued.append((entity_id, connectors, requested_by, parent_job_id))
        return Job(f"child-{entity_id}", entity_id, entity_id, ["gleif"], parent_job_id=parent_job_id)

    monkeypatch.setattr("illuminate.enrichment.worker.db.read", suppliers)
    monkeypatch.setattr(checkpoints, "save", lambda job: _async_none())
    monkeypatch.setattr(worker, "enqueue", enqueue)

    await worker._enqueue_supplier_enrichment(parent)

    assert queued == [
        ("supplier-1", None, "program-discovery", "parent"),
        ("supplier-2", None, "program-discovery", "parent"),
    ]
    assert parent.results["_supplier_enrichment"]["queued"] == 2
    assert parent.results["_supplier_enrichment"]["child_job_ids"] == [
        "child-supplier-1", "child-supplier-2",
    ]


async def test_fresh_worker_retires_abandoned_process_checkpoints(monkeypatch):
    from illuminate.enrichment import checkpoints
    calls = []

    async def interrupt():
        calls.append("interrupted")
        return 2

    monkeypatch.setattr(checkpoints, "interrupt_active", interrupt)
    worker = Worker()
    assert await worker.recover_interrupted() == 2
    assert calls == ["interrupted"]


async def test_checkpoint_interruption_reads_write_result_rows(monkeypatch):
    from illuminate.enrichment import checkpoints

    async def write(*args, **kwargs):
        return {"rows": [{"count": 3}], "counters": {"properties_set": 6}}

    monkeypatch.setattr(checkpoints.db, "write", write)
    assert await checkpoints.interrupt_active() == 3


async def _async_none():
    return None


async def _record_async(target, value):
    target.append(value)