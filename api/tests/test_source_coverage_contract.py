import asyncio

from illuminate.connectors import contextual
from illuminate.connectors.registry import REGISTRY, coverage_contract, get_connector, source_metadata
from illuminate.connectors.source_contract import SOURCE_COVERAGE


NDIA_IDS = {f"ndia:{value}" for value in (
    1, 36, 38, 40, 43, 45, 47, 49, 56, 57, 61, 62, 64, 70, 114, 115, 118, 128,
)}


def test_approved_ndia_contract_is_complete_and_actionable():
    records = coverage_contract()
    ndia_ids = {catalog_id for record in records for catalog_id in record["catalog_ids"]}
    assert ndia_ids == NDIA_IDS
    registry_names = {connector.name for connector in REGISTRY}
    for record in records:
        assert record["source_id"]
        assert record["endpoint"].startswith("https://")
        assert record["access"]
        assert record["credentials"]
        assert record["freshness"]
        assert record["entity_kinds"]
        assert record["categories"]
        assert record["limitations"]
        if record["adapter"]:
            assert record["adapter"] in registry_names
        else:
            assert record["policy_status"] in {"unavailable", "not_applicable"}
            assert record["action"]


def test_coverage_contract_returns_a_deep_copy():
    first = coverage_contract()
    first[0]["catalog_ids"].append("ndia:changed")
    assert "ndia:changed" not in SOURCE_COVERAGE[0]["catalog_ids"]


def test_contextual_connector_metadata_preserves_contract_provenance():
    expected = {
        "openstreetmap": ("openstreetmap", "ndia:115"),
        "far": ("ecfr-title-48", "ndia:118"),
        "epss": ("first-epss", "ndia:128"),
    }
    for name, (source_id, catalog_id) in expected.items():
        data = get_connector(name).to_dict()
        assert data["source_id"] == source_id
        assert data["catalog_ids"] == [catalog_id]
        assert data["endpoint"].startswith("https://")
        assert data["freshness"]
        assert data["categories"]
        assert data["limitations"]
        assert source_metadata(name)["catalog_ids"] == [catalog_id]
        assert "status" not in data
        assert data["policy_status"] == "available"


def test_epss_adapter_is_contextual_bounded_and_preserves_identifier(monkeypatch):
    calls = []

    async def fake_fetch(method, url, *, params=None, ttl=None):
        calls.append((method, url, params, ttl))
        return {"data": [{
            "cve": "CVE-2021-44228", "epss": "0.975", "percentile": "0.999",
            "date": "2026-09-08",
        }]}

    monkeypatch.setattr(contextual, "fetch_json", fake_fetch)
    connector = get_connector("epss")
    assert connector.applies_to({"kind": "organization"}) is False
    entity = {"id": "ent_1", "kind": "organization", "cves": ["bad", "CVE-2021-44228"]}
    facts = asyncio.run(connector.enrich(entity, "local"))
    assert len(calls) == 1
    assert calls[0][2] == {"cve": "CVE-2021-44228"}
    assert [fact.predicate for fact in facts] == ["vulnerability_screen", "cyber_screen"]
    assert all(fact.props["cve"] == "CVE-2021-44228" for fact in facts)
    assert all(
        fact.artifact.props["source_identifier"] == "CVE-2021-44228:2026-09-08"
        for fact in facts
    )
    cyber = facts[1]
    assert cyber.value == "high"
    assert cyber.props["epss_probability"] == 0.975
    assert cyber.confidence == 1.0


def test_osm_and_far_do_not_read_without_explicit_context(monkeypatch):
    async def fail(*args, **kwargs):
        raise AssertionError("source should not be read")

    monkeypatch.setattr(contextual, "fetch_json", fail)
    monkeypatch.setattr(contextual, "fetch_document", fail)
    base = {"id": "ent_1", "kind": "organization", "name": "Example"}
    assert asyncio.run(get_connector("openstreetmap").enrich(base, "local")) == []
    assert asyncio.run(get_connector("far").enrich(base, "local")) == []


def test_far_adapter_asserts_only_when_retrieved_document_contains_clause(monkeypatch):
    async def document(*args, **kwargs):
        return {"body": b"<html>52.204-21 Basic Safeguarding</html>"}

    monkeypatch.setattr(contextual, "fetch_document", document)
    entity = {"id": "ent_1", "kind": "program", "far_clause": "52.204-21"}
    facts = asyncio.run(get_connector("far").enrich(entity, "local"))
    assert len(facts) == 1
    assert facts[0].predicate == "far_clause_screen"

    async def unrelated(*args, **kwargs):
        return {"body": b"<html>FAR part 52 index only</html>"}

    monkeypatch.setattr(contextual, "fetch_document", unrelated)
    assert asyncio.run(get_connector("far").enrich(entity, "local")) == []


def test_contextual_predicates_are_committing_observations():
    from illuminate.enrichment.claims import OBSERVATION_PREDICATES

    assert {"vulnerability_screen", "cyber_screen", "far_clause_screen", "location_context_screen"} <= OBSERVATION_PREDICATES