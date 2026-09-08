import csv
import asyncio
import hashlib
import io
import json

import pytest
from httpx import ASGITransport, AsyncClient

from illuminate.main import app
from illuminate.routers import exports


ROWS = [
    {
        "claim_id": "clm_1", "predicate": "sole_source_dependency", "object_value": True,
        "detail": "one source", "risk_score": 75, "risk_level": "high", "risk_category": "concentration",
        "risk_rationale": "one source", "recommendation": "qualify another source", "source": "USAspending",
        "source_id": "usaspending-v2", "source_identifier": "award-123", "catalog_ids": ["ndia:1"],
        "source_url": "https://example.test/award", "retrieved_at": "2026-09-08T10:00:00Z",
        "usage_note": "public domain", "quality_note": "award record",
        "supports": "federal award linkage", "unknowns": "does not prove performance",
        "source_status": "retrieved",
        "method": "connector", "confidence": .9, "classification": "UNCLASSIFIED", "license": "CC0-1.0",
        "quality_score": .9, "completeness": .8, "quality_notes": None, "status": "committed",
        "claim_simulated": False, "subject_id": "ent_1", "subject_type": "Entity",
        "subject_name": "Supplier", "subject_simulated": False, "object_id": None, "object_type": None,
        "targets": [], "artifacts": [], "observed": "2026-09-08T10:00:00Z",
        "identity_key": "clm_1|ent_1",
    },
    {
        "claim_id": "clm_2", "predicate": "foreign_control", "object_value": None,
        "status": "staged", "claim_simulated": True, "subject_id": "ent_2", "subject_type": "Entity",
        "subject_name": "Scenario Supplier", "subject_simulated": False,
        "targets": [{"id": "loc_CN", "type": "Location", "name": "China", "simulated": False}],
        "artifacts": [{"id": "art_1", "title": "Registry", "source": "registry", "source_url": "https://example.test",
                       "retrieved_at": "2026-09-08T11:00:00Z", "simulated": False,
                       "evidence_present": True, "evidence_source": "OpenCorporates",
                       "evidence_source_id": "opencorporates-v0.4",
                       "evidence_retrieved_at": "2026-09-08T11:00:00Z",
                       "evidence_usage_note": "subject to provider terms",
                       "evidence_quality_note": "jurisdiction coverage varies",
                       "evidence_supports": "company registry discovery",
                       "evidence_unknowns": "does not establish beneficial ownership",
                       "evidence_source_status": "retrieved", "evidence_simulated": False}],
        "observed": "2026-09-08T11:00:00Z",
        "identity_key": "clm_2|ent_2",
    },
]


@pytest.fixture
def fake_db(monkeypatch):
    events = [
        {"finding_id": exports._stable_finding_id(row), "revision": i + 1,
         "payload": exports._finding(row).model_dump_json()}
        for i, row in enumerate(ROWS)
    ]

    async def sync():
        return len(events)

    async def read(query, params):
        if query == exports._LATEST_EVENTS:
            return sorted(
                [event for event in events if event["finding_id"] > params["after_id"]],
                key=lambda event: event["finding_id"],
            )[:params["fetch"]]
        if query == exports._INCREMENTAL_EVENTS:
            after = (params["after_revision"], params["after_id"])
            return [event for event in events
                    if (event["revision"], event["finding_id"]) > after
                    and event["revision"] > params["since_revision"]
                    and event["revision"] <= params["upper"]][:params["fetch"]]
        raise AssertionError("unexpected query")

    monkeypatch.setattr(exports, "_sync_export_ledger", sync)
    monkeypatch.setattr(exports.db, "read", read)


async def test_schema_and_canonical_page_validate(fake_db):
    page = await exports._page(10, None, None, False)
    validated = exports.FindingPage.model_validate(page.model_dump())
    assert validated.meta.count == 2
    risk_finding = next(f for f in validated.findings if f.risk.score == 75)
    simulated_finding = next(f for f in validated.findings if f.simulated)
    assert risk_finding.object_value is True
    claim_lineage = next(item for item in risk_finding.provenance if item.scope == "claim")
    assert claim_lineage.catalog_ids == ["ndia:1"]
    assert claim_lineage.source_identifier == "award-123"
    evidence_lineage = next(item for item in simulated_finding.provenance if item.scope == "evidence")
    assert evidence_lineage.source_id == "opencorporates-v0.4"
    assert evidence_lineage.unknowns == "does not establish beneficial ownership"
    assert {p.edges[0].type for p in simulated_finding.paths} == {"ASSERTS", "TARGETS", "EVIDENCES"}
    for finding in validated.findings:
        claim_id = next(item.claim_id for item in finding.provenance if item.scope == "claim")
        claim_nodes = {
            node.id
            for path in finding.paths
            for node in path.nodes
            if node.type == "Claim"
        }
        assert claim_nodes == {claim_id}
        assert all(
            edge.source == claim_id
            for path in finding.paths
            for edge in path.edges
            if edge.type in {"ASSERTS", "TARGETS"}
        )
        assert all(
            edge.target == claim_id
            for path in finding.paths
            for edge in path.edges
            if edge.type == "EVIDENCES"
        )
    assert "properties" in exports.FindingPage.model_json_schema()


async def test_repeatable_cursor_and_incremental_watermark(fake_db):
    first = await exports._page(1, None, None, False)
    assert first.meta.next_cursor
    second = await exports._page(1, first.meta.next_cursor, None, False)
    assert [f.finding_id for f in first.findings + second.findings] == sorted([
        exports._stable_finding_id(ROWS[0]), exports._stable_finding_id(ROWS[1]),
    ])
    empty = await exports._page(10, None, second.meta.watermark, False, incremental=True)
    assert empty.findings == []


async def test_public_http_contract_is_registered(fake_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        schema = await client.get("/api/exports/v1/schema")
        fields = await client.get("/api/exports/v1/fields")
        sample = await client.get("/api/exports/v1/sample")
        first = await client.get("/api/exports/v1/findings", params={"limit": 1})
        assert schema.status_code == fields.status_code == sample.status_code == first.status_code == 200
        assert schema.json()["schema"]["title"] == "FindingPage"
        assert "truth_status" in fields.json()["fields"]
        assert sample.json()["finding"]["finding_id"].startswith("fnd_")

        first_page = first.json()
        second = await client.get("/api/exports/v1/findings", params={
            "limit": 1, "cursor": first_page["meta"]["next_cursor"],
        })
        assert second.status_code == 200
        assert second.json()["findings"][0]["finding_id"] != first_page["findings"][0]["finding_id"]

        incremental = await client.get("/api/exports/v1/findings/incremental", params={
            "since": first_page["meta"]["watermark"],
        })
        assert incremental.status_code == 200
        assert incremental.json()["findings"] == []

        ndjson = await client.get("/api/exports/v1/findings", params={"limit": 1, "format": "ndjson"})
        csv_download = await client.get("/api/exports/v1/findings", params={"limit": 1, "format": "csv"})
        assert ndjson.status_code == csv_download.status_code == 200
        assert ndjson.headers["content-type"].startswith("application/x-ndjson")
        assert csv_download.headers["content-type"].startswith("text/csv")
        assert json.loads(ndjson.text)["finding_id"].startswith("fnd_")
        assert next(csv.DictReader(io.StringIO(csv_download.text)))["finding_id"]


@pytest.mark.parametrize(
    ("params", "status"),
    [
        ({"limit": 0}, 422),
        ({"limit": exports.MAX_LIMIT + 1}, 422),
        ({"format": "xml"}, 422),
        ({"cursor": "not-a-token"}, 400),
    ],
)
async def test_public_http_contract_rejects_invalid_page_requests(fake_db, params, status):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/exports/v1/findings", params=params)
    assert response.status_code == status

async def test_incremental_contract_rejects_malformed_watermark(fake_db):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/exports/v1/findings/incremental",
            params={"since": "not-a-token"},
        )
    assert response.status_code == 400
async def test_rejected_findings_are_filterable_and_cursor_preserves_policy(monkeypatch):
    rows = [dict(ROWS[0]), {**ROWS[1], "status": "rejected"}]
    events = [
        {"finding_id": exports._stable_finding_id(row), "revision": i + 1,
         "payload": exports._finding(row).model_dump_json()}
        for i, row in enumerate(rows)
    ]

    async def sync():
        return len(events)

    async def read(query, params):
        selected = [
            event for event in events
            if event["finding_id"] > params["after_id"]
            and (params["include_rejected"]
                 or exports.Finding.model_validate_json(event["payload"]).truth_status != "rejected")
        ]
        return sorted(selected, key=lambda event: event["finding_id"])[:params["fetch"]]

    monkeypatch.setattr(exports, "_sync_export_ledger", sync)
    monkeypatch.setattr(exports.db, "read", read)

    excluded = await exports._page(1, None, None, False)
    included = await exports._page(1, None, None, True)
    assert [finding.truth_status for finding in excluded.findings] == ["committed"]
    assert included.meta.next_cursor

    continued = await exports._page(10, included.meta.next_cursor, None, False)
    assert {finding.truth_status for finding in included.findings + continued.findings} == {
        "committed", "rejected",
    }


async def test_formats_are_lossless(fake_db):
    page = await exports._page(10, None, None, False)
    ndjson = exports._render(page, "ndjson")
    ndjson_rows = [json.loads(line) for line in ndjson.body.splitlines()]
    assert next(row for row in ndjson_rows if row["risk"]["score"] == 75)
    csv_response = exports._render(page, "csv")
    row = next(row for row in csv.DictReader(io.StringIO(csv_response.body.decode()))
               if json.loads(row["risk"])["score"] == 75)
    assert json.loads(row["risk"])["score"] == 75
    assert json.loads(row["paths"])[0]["edges"][0]["type"] == "ASSERTS"
    assert json.loads(row["detail"]) == "one source"
    assert json.loads(row["object_id"]) is None


def test_stable_fallback_id():
    row = {"claim_id": "clm_1", "subject_id": "ent_1", "predicate": "p", "object_value": "x"}
    assert exports._stable_finding_id(row) == exports._stable_finding_id(dict(row))
    assert exports._stable_finding_id(row).startswith("fnd_")

@pytest.mark.parametrize("status", ["staged", "committed", "rejected"])
def test_truth_status_and_simulation_survive_export_projection(status):
    row = {
        **ROWS[0],
        "claim_id": f"clm_{status}",
        "identity_key": f"clm_{status}|ent_1",
        "status": status,
        "claim_simulated": status == "staged",
    }
    finding = exports._finding(row)

    assert finding.truth_status == status
    assert finding.simulated is (status == "staged")
    assert finding.finding_id == exports._stable_finding_id(row)
    assert finding.finding_id != row["claim_id"]
    assert finding.paths[0].nodes[0].id == row["claim_id"]
def test_all_targets_are_exported_in_order():
    row = dict(ROWS[1])
    row["targets"] = [
        {"id": "loc_CA", "type": "Location", "name": "Canada", "simulated": False},
        {"id": "loc_CN", "type": "Location", "name": "China", "simulated": True},
    ]
    finding = exports._finding(row)
    assert finding.object_id == "loc_CA"
    assert [p.nodes[-1].id for p in finding.paths if p.edges[0].type == "TARGETS"] == ["loc_CA", "loc_CN"]
    assert finding.simulated is True


def test_linked_metadata_changes_payload_at_same_observation_time():
    before = exports._finding(ROWS[1]).model_dump_json()
    changed = dict(ROWS[1])
    changed["subject_name"] = "Renamed Scenario Supplier"
    changed["artifacts"] = [dict(
        ROWS[1]["artifacts"][0],
        evidence_source_status="updated",
        evidence_catalog_ids=["ndia:future"],
    )]
    after = exports._finding(changed).model_dump_json()
    assert changed["observed"] == ROWS[1]["observed"]
    assert hashlib.sha256(before.encode()).digest() != hashlib.sha256(after.encode()).digest()


def test_token_shape_is_validated():
    malformed = exports._token({"v": exports.VERSION, "kind": "watermark"})
    with pytest.raises(exports.HTTPException) as exc:
        exports._untoken(malformed, "watermark")
    assert exc.value.status_code == 400


async def test_concurrent_syncs_are_serialized(monkeypatch):
    owner = None
    completed_at = "1970-01-01T00:00:00Z"
    state_lock = asyncio.Lock()
    active_scans = 0
    max_active_scans = 0
    releases = []

    async def write(query, params):
        nonlocal owner, completed_at
        async with state_lock:
            if query == exports._ACQUIRE_LOCK:
                if owner is None:
                    owner = params["owner"]
                    return {"rows": [{"owner": owner, "completed_at": completed_at}], "counters": {}}
                return {"rows": [], "counters": {}}
            if query == exports._RELEASE_LOCK and owner == params["owner"]:
                releases.append(params["completed"])
                if params["completed"]:
                    completed_at = exports._utc_now().isoformat()
                owner = None
            return {"rows": [{"released": True}], "counters": {}}

    async def read(query, params):
        nonlocal active_scans, max_active_scans
        if query == exports._UPPER:
            active_scans += 1
            max_active_scans = max(max_active_scans, active_scans)
            await asyncio.sleep(0.03)
            active_scans -= 1
            return []
        if query == exports._MISSING_STATES:
            return []
        if query == exports._COUNTER:
            return [{"value": 0}]
        raise AssertionError("unexpected query")

    monkeypatch.setattr(exports.db, "write", write)
    monkeypatch.setattr(exports.db, "read", read)
    assert await asyncio.gather(exports._sync_export_ledger(), exports._sync_export_ledger()) == [0, 0]
    assert max_active_scans == 1
    assert sorted(releases) == [False, True]


async def test_removed_finding_emits_tombstone(monkeypatch):
    source = exports._finding(ROWS[0])
    writes = []
    missing_reads = 0

    async def write(query, params):
        nonlocal writes
        if query in {exports._ACQUIRE_LOCK, exports._RENEW_LOCK}:
            return {"rows": [{"owner": params["owner"], "completed_at": "1970-01-01T00:00:00Z"}], "counters": {}}
        if query == exports._UPSERT_EVENTS:
            writes.extend(params["records"])
        return {"rows": [{"ok": True}], "counters": {}}

    async def read(query, params):
        nonlocal missing_reads
        if query == exports._UPPER:
            return []
        if query == exports._MISSING_STATES:
            missing_reads += 1
            return ([{"finding_id": source.finding_id, "payload": source.model_dump_json()}]
                    if missing_reads == 1 else [])
        if query == exports._COUNTER:
            return [{"value": 2}]
        raise AssertionError("unexpected query")

    monkeypatch.setattr(exports.db, "write", write)
    monkeypatch.setattr(exports.db, "read", read)
    assert await exports._sync_export_ledger() == 2
    assert len(writes) == 1 and writes[0]["deleted"] is True
    assert exports.Finding.model_validate_json(writes[0]["payload"]).deleted is True


async def test_concurrently_updated_association_is_not_tombstoned(monkeypatch):
    writes = []

    async def write(query, params):
        if query in {exports._ACQUIRE_LOCK, exports._RENEW_LOCK}:
            return {"rows": [{"owner": params["owner"], "completed_at": "1970-01-01T00:00:00Z"}], "counters": {}}
        if query == exports._UPSERT_EVENTS:
            writes.extend(params["records"])
        return {"rows": [{"ok": True}], "counters": {}}

    async def read(query, params):
        if query == exports._UPPER:
            return [{"observed": ROWS[0]["observed"], "id": ROWS[0]["identity_key"]}]
        if query == exports._SELECT:
            return []  # the claim moved beyond the captured upper bound
        if query == exports._MISSING_STATES:
            assert "NOT EXISTS" in query  # live association check retains the finding
            return []
        if query == exports._COUNTER:
            return [{"value": 1}]
        raise AssertionError("unexpected query")

    monkeypatch.setattr(exports.db, "write", write)
    monkeypatch.setattr(exports.db, "read", read)
    assert await exports._sync_export_ledger() == 1
    assert writes == []

async def test_incremental_contract_rejects_tampered_and_future_watermarks(fake_db):
    valid = exports._token({
        "v": exports.VERSION,
        "kind": "watermark",
        "position": ["1", ""],
    })
    encoded, signature = valid.split(".")
    tampered_payload = json.loads(
        __import__("base64").urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    )
    tampered_payload["position"][0] = "999"
    tampered_encoded = __import__("base64").urlsafe_b64encode(
        json.dumps(tampered_payload, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        tampered = await client.get(
            "/api/exports/v1/findings/incremental",
            params={"since": f"{tampered_encoded}.{signature}"},
        )
        future = await client.get(
            "/api/exports/v1/findings/incremental",
            params={"since": exports._token({
                "v": exports.VERSION,
                "kind": "watermark",
                "position": ["999", ""],
            })},
        )
    assert tampered.status_code == 400
    assert future.status_code == 409
