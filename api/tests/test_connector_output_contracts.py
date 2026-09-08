"""Representative provider fixtures exercising every real registry adapter."""
from types import SimpleNamespace

import pytest

from illuminate.connectors import (
    contextual, edgar, gdelt, gleif, littlesis, market, ofac,
    opencorporates, sam, sam_exclusions, un_sanctions, usaspending, websearch,
)
from illuminate.connectors.registry import REGISTRY, get_connector
from illuminate.connectors.validation import validate_facts


async def _none(*args, **kwargs):
    return None


async def _empty(*args, **kwargs):
    return []


async def _facts_for(name, monkeypatch):
    entity = {"id": "ent_fixture", "name": "Fixture Corp", "kind": "organization"}

    if name == "sam":
        monkeypatch.setattr(sam.vault(), "get", lambda *args: "configured")
        async def fetch(*args, **kwargs):
            return {"entityData": [{
                "entityRegistration": {
                    "ueiSAM": "FIXTUREUEI123", "legalBusinessName": "Fixture Corp",
                    "registrationStatus": "Active",
                },
                "coreData": {"generalInformation": {}},
            }]}
        monkeypatch.setattr(sam, "fetch_json", fetch)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "sam_exclusions":
        monkeypatch.setattr(sam_exclusions, "refresh_index", _none)
        monkeypatch.setattr(sam_exclusions, "screen", lambda *args: {
            "result": "clear", "hits": [], "extract": "fixture.csv", "index_size": 1,
        })
        return await get_connector(name).enrich(entity, "fixture")

    if name == "usaspending":
        async def awards(*args, **kwargs):
            return {"results": [{
                "generated_internal_id": "AWARD_FIXTURE_1", "Award ID": "FAKE-1",
                "Description": "Fixture award", "Recipient UEI": "FIXTUREUEI123",
                "PSC": "1510", "Start Date": "2026-01-02",
            }]}
        monkeypatch.setattr(usaspending, "awards_for_recipient", awards)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "gleif":
        entity["lei"] = "549300FIXTURELEI"
        async def record(*args):
            return {"id": entity["lei"], "attributes": {"entity": {
                "legalName": {"name": "Fixture Corp"}, "legalAddress": {"country": "US"},
            }, "registration": {"status": "ISSUED"}}}
        monkeypatch.setattr(gleif, "lei_record", record)
        monkeypatch.setattr(gleif, "parent", _none)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "littlesis":
        async def org(*args):
            return {"id": 42, "name": "Fixture Corp", "types": ["Business"], "aliases": ["Fixture"]}
        monkeypatch.setattr(littlesis, "find_org", org)
        monkeypatch.setattr(littlesis, "people_facts", lambda *args: _people())
        monkeypatch.setattr(littlesis, "affiliation_facts", _empty)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "edgar":
        entity["cik"] = 123
        async def submissions(*args):
            return {
                "name": "Fixture Corp", "tickers": ["FIX"], "stateOfIncorporation": "DE",
                "filings": {"recent": {
                    "form": ["10-K"], "filingDate": ["2026-01-02"],
                    "accessionNumber": ["0001-02"], "primaryDocument": ["report.htm"],
                }},
            }
        monkeypatch.setattr(edgar, "submissions", submissions)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "gdelt":
        async def articles(*args, **kwargs):
            return {"articles": [{
                "url": "http://publisher.example/fixture", "title": "Fixture article",
                "seendate": "20260908T120000Z", "domain": "publisher.example",
            }]}
        monkeypatch.setattr(gdelt, "fetch_json", articles)
        from illuminate.llm import tasks
        monkeypatch.setattr(tasks, "sentiment", _none)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "ofac":
        async def screening(*args, **kwargs):
            return {"result": "clear", "hits": [], "list_size": 1}
        monkeypatch.setattr(ofac, "screen_name", screening)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "un_sanctions":
        async def listing():
            return {
                "generated": "2026-09-08",
                "entities": [{
                    "dataid": "1", "name": "Fixture Corp", "aliases": [],
                    "reference": "CDe.001", "regime": "Fixture", "listed_on": "2026-01-02",
                    "comments": "",
                }],
                "individuals": [],
            }
        monkeypatch.setattr(un_sanctions, "consolidated_list", listing)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "market":
        entity["ticker"] = "FIX"
        monkeypatch.setattr(market.vault(), "get", lambda *args: "configured")
        async def quote(method, url, **kwargs):
            return {"c": 12.5} if url.endswith("/quote") else {"marketCapitalization": 250}
        monkeypatch.setattr(market, "fetch_json", quote)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "opencorporates":
        monkeypatch.setattr(opencorporates.vault(), "get", lambda *args: "configured")
        async def companies(*args, **kwargs):
            return {"results": {"companies": [{"company": {
                "name": "Fixture Corp", "jurisdiction_code": "us_de",
                "company_number": "123", "opencorporates_url": "http://registry.example/123",
                "incorporation_date": "2020-01-02",
            }}]}}
        monkeypatch.setattr(opencorporates, "fetch_json", companies)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "openstreetmap":
        entity.update(latitude=38.9, longitude=-77.0)
        async def reverse(*args, **kwargs):
            return {"osm_type": "way", "osm_id": 123, "display_name": "Fixture Place"}
        monkeypatch.setattr(contextual, "fetch_json", reverse)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "far":
        entity["far_clause"] = "52.204-21"
        async def document(*args, **kwargs):
            return {"body": b"52.204-21 Basic Safeguarding"}
        monkeypatch.setattr(contextual, "fetch_document", document)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "epss":
        entity["cves"] = ["CVE-2021-44228"]
        async def epss(*args, **kwargs):
            return {"data": [{
                "cve": "CVE-2021-44228", "epss": "0.9",
                "percentile": "0.99", "date": "2026-09-08",
            }]}
        monkeypatch.setattr(contextual, "fetch_json", epss)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "websearch":
        response = SimpleNamespace(
            output_text="Fixture research",
            output=[SimpleNamespace(content=[SimpleNamespace(annotations=[
                SimpleNamespace(url="http://publisher.example/citation"),
            ])])],
        )
        client = SimpleNamespace(responses=SimpleNamespace(
            create=lambda **kwargs: _response(response)
        ))
        monkeypatch.setattr(websearch, "client_for", lambda *args: client)
        monkeypatch.setattr(websearch, "models", lambda *args: ("fixture-model", "fixture-model"))
        async def extracted(*args, **kwargs):
            return [{"predicate": "INCORPORATED_IN", "object": "US", "confidence": 0.7}]
        monkeypatch.setattr(websearch, "extract_facts", extracted)
        return await get_connector(name).enrich(entity, "fixture")

    if name == "openai":
        return await get_connector(name).enrich(entity, "fixture")

    raise AssertionError(f"missing fixture for {name}")


async def _people():
    return [], None


async def _response(value):
    return value


@pytest.mark.parametrize("connector", REGISTRY, ids=lambda connector: connector.name)
async def test_real_connector_output_matches_production_fact_contract(connector, monkeypatch):
    facts = await _facts_for(connector.name, monkeypatch)
    validate_facts(connector.name, facts)
    assert all(fact.subject.id and fact.predicate for fact in facts)
    assert all(0 <= fact.confidence <= 1 for fact in facts)
    assert all(
        fact.artifact is None or (fact.artifact.source and fact.artifact.title)
        for fact in facts
    )
    if connector.name != "openai":
        assert facts, f"{connector.name} fixture did not exercise normalization"


async def test_provider_fixtures_preserve_source_specific_identity_and_time(monkeypatch):
    by_name = {
        name: await _facts_for(name, monkeypatch)
        for name in ("sam", "usaspending", "edgar", "gdelt", "openstreetmap", "far", "epss")
    }
    assert any(f.value == "FIXTUREUEI123" for f in by_name["sam"])
    assert any(f.artifact.props.get("award_id") == "FAKE-1" for f in by_name["usaspending"])
    assert any(f.artifact.published_at == "2026-01-02" for f in by_name["edgar"])
    assert any(f.artifact.published_at == "2026-09-08" for f in by_name["gdelt"])
    assert by_name["openstreetmap"][0].artifact.props["source_identifier"] == "way/123"
    assert by_name["far"][0].artifact.props["source_identifier"] == "52.204-21"
    assert by_name["epss"][0].artifact.props["source_identifier"] == "CVE-2021-44228:2026-09-08"