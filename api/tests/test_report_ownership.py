from __future__ import annotations

from pathlib import Path

import pytest

import illuminate.report as report


@pytest.mark.asyncio
async def test_ownership_records_keep_claim_states_artifacts_and_missing_values(monkeypatch):
    calls = 0

    async def read(_query, _params):
        nonlocal calls
        calls += 1
        if calls == 1:
            return [{
                "owner_id": "ent_parent", "owner_name": "Parent", "owner_kind": "organization",
                "predicate": "OWNS", "claim_id": "clm_staged", "claim_status": "staged",
                "claim_source": "registry", "claim_retrieved_at": "2000-09-08T00:00:00Z",
                "claim_method": "connector", "claim_confidence": .7,
                "claim_simulated": False, "owner_simulated": False,
                "relationship_id": None, "relationship_simulated": False,
                "percentage": None, "effective_date": None, "as_of_date": None,
                "artifacts": [{"id": "art_1", "url": "https://example.test/record",
                               "simulated": False, "evidence_simulated": False}],
            }, {
                "owner_id": "per_owner", "owner_name": "Scenario Owner", "owner_kind": "Person",
                "predicate": "BENEFICIAL_OWNER_OF", "claim_id": "clm_rejected",
                "claim_status": "rejected", "claim_source": "open-source",
                "claim_simulated": False, "owner_simulated": False,
                "relationship_id": None, "relationship_simulated": False,
                "percentage": 25, "effective_date": "2026-01-01", "as_of_date": None,
                "artifacts": [{"id": "art_sim", "simulated": False, "evidence_simulated": True}],
            }]
        return [{
            "owner_id": "ent_legacy", "owner_name": "Legacy Parent", "owner_kind": "Entity",
            "predicate": "ULTIMATE_PARENT_OF", "relationship_id": "rel_legacy",
            "relationship_simulated": False, "owner_simulated": False,
            "percentage": None, "effective_date": None, "as_of_date": None, "artifacts": [],
        }]

    monkeypatch.setattr(report.db, "read", read)
    records = await report.ownership_records("ent_target")

    assert [record["relationship_type"] for record in records] == [
        "direct", "beneficial_owner", "ultimate_parent",
    ]
    assert records[0]["truth_status"] == "staged"
    assert records[0]["freshness"] == "stale"
    assert records[0]["evidence_present"] is True
    assert records[0]["percentage"] is None
    assert records[1]["truth_status"] == "rejected"
    assert records[1]["simulated"] is True
    assert records[2]["truth_status"] == "unsupported"
    assert records[2]["claim"] is None
    assert records[2]["evidence_present"] is False


def test_ownership_contract_uses_current_claim_not_relationship_status():
    record = report._ownership_record({
        "owner_id": "ent_parent", "owner_name": "Parent", "owner_kind": "Entity",
        "predicate": "OWNS", "claim_id": "clm_1", "claim_status": "rejected",
        "relationship_id": "rel_1", "relationship_status": "committed",
        "artifacts": [],
    }, relationship_present=True)
    assert record["truth_status"] == "conflicting"
    assert record["claim"]["status"] == "rejected"
    assert record["conflicting"] is True
    assert record["relationship"]["present"] is True
    assert record["evidence_present"] is False


def test_committed_ownership_without_artifact_is_not_verified():
    record = report._ownership_record({
        "owner_id": "ent_parent", "owner_name": "Parent", "owner_kind": "Entity",
        "predicate": "ULTIMATE_PARENT_OF", "claim_id": "clm_1",
        "claim_status": "committed", "claim_retrieved_at": "2026-09-08T00:00:00Z",
        "relationship_id": "rel_1", "artifacts": [],
    }, relationship_present=True)
    assert record["claim"]["status"] == "committed"
    assert record["truth_status"] == "unsupported"


def test_superseded_committed_claim_is_not_current_or_verified():
    record = report._ownership_record({
        "owner_id": "ent_old_parent", "owner_name": "Old Parent", "owner_kind": "Entity",
        "predicate": "OWNS", "claim_id": "clm_old", "claim_status": "committed",
        "claim_retrieved_at": "2000-09-08T00:00:00Z", "relationship_id": None,
        "artifacts": [{"id": "art_old"}],
    }, relationship_present=False)
    assert record["truth_status"] == "superseded"
    assert record["freshness"] == "stale"
    assert record["current"] is False
    assert record["claim"]["status"] == "committed"


def test_entity_report_presents_ownership_lineage_and_missing_states():
    web = Path(__file__).parents[2] / "web" / "src"
    report_view = (web / "views" / "EntityReport.vue").read_text()
    claims_view = (web / "views" / "Claims.vue").read_text()

    for label in ("Percentage", "Effective", "As of", "Claim", "Source", "Retrieved", "Method", "Confidence"):
        assert f"<dt>{label}</dt>" in report_view
    assert "No backing claim — unsupported" in report_view
    assert "No backing artifact available" in report_view
    assert "claim_id: o.claim.id" in report_view
    assert "@click=\"rawId = a.id\"" in report_view
    assert "claim_id=${encodeURIComponent(claimId)}" in claims_view