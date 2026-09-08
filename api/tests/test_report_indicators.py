from __future__ import annotations

from datetime import date

import pytest

import illuminate.report as report_module
from illuminate.report import build_report, evaluate_risk_contract, risk_indicators


def core(*, simulated: bool = False) -> dict:
    return {
        "e": {"id": "vendor", "name": "Vendor", "simulated": simulated},
        "parent_seat": None,
        "ultimate_parents": [],
    }


def people() -> dict:
    return {"current": [], "former": []}


def async_value(value):
    async def load(*_args, **_kwargs):
        return value
    return load


@pytest.mark.asyncio
async def test_sole_source_indicator_links_graph_edge_and_evidence():
    supply = {
        "supplies": [{
            "id": "consumer",
            "edge_id": "supply-edge",
            "tier": 2,
            "sole_source": True,
            "source": "USAspending",
            "source_url": "https://example.test/award",
            "simulated": True,
        }],
    }
    risk = await risk_indicators("vendor", core(), supply, people(), [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "concentration")
    assert indicator["element_ids"] == ["supply-edge"]
    assert indicator["source_url"] == "https://example.test/award"
    assert indicator["simulated"] is True


@pytest.mark.asyncio
async def test_supply_indicator_inherits_backing_evidence_simulation():
    display = {
        "id": "consumer",
        "edge_id": "supply-edge",
        "tier": 2,
        "sole_source": True,
        "contract_ref": "award",
        "source": "USAspending",
        "source_url": "https://example.test/award",
        "simulated": False,
    }
    backing = {
        "evidence_id": "supply-edge",
        "claim_id": "supply-claim",
        "contract_ref": "award",
        "source_url": "https://example.test/backing",
        "artifact_simulated": False,
        "evidence_simulated": True,
    }
    risk = await risk_indicators(
        "vendor",
        core(),
        {"supplies": [display], "risk_evidence": [backing]},
        people(),
        [],
    )
    indicator = next(i for i in risk["indicators"] if i["family"] == "concentration")
    assert indicator["simulated"] is True
    assert indicator["element_ids"] == ["supply-edge", "supply-claim"]


@pytest.mark.asyncio
async def test_ownership_indicator_inherits_backing_evidence_simulation():
    data = core()
    data["parent_seat"] = {
        "id": "location",
        "code": "CN",
        "relationship_id": "seat-edge",
        "simulated": False,
    }
    data["parent_seat_evidence"] = [{
        "id": "seat-edge",
        "claim_id": "seat-claim",
        "seat_code": "CN",
        "artifact_simulated": False,
        "evidence_simulated": True,
        "source_url": "https://example.test/seat-evidence",
    }]
    risk = await risk_indicators("vendor", data, {"supplies": []}, people(), [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "ownership")
    assert indicator["simulated"] is True
    assert indicator["element_ids"] == ["location", "seat-edge", "seat-claim"]
    assert indicator["source_url"] == "https://example.test/seat-evidence"


@pytest.mark.asyncio
async def test_screen_indicator_links_claim_artifact_and_relationships():
    artifact = {
        "id": "artifact",
        "url": "https://example.test/evidence",
        "evidence_edge_id": "evidence-edge",
        "simulated": False,
        "evidence_simulated": True,
    }
    screens = [{
        "predicate": "sanctions_screen",
        "result": "hit",
        "source": "screen",
        "detail": "scenario hit",
        "claim_id": "claim",
        "asserts_edge_id": "asserts-edge",
        "simulated": False,
        "artifact": artifact,
    }]
    risk = await risk_indicators("vendor", core(), {"supplies": []}, people(), screens)
    indicator = next(i for i in risk["indicators"] if i["family"] == "sanctions")
    assert indicator["element_ids"] == ["claim", "asserts-edge", "artifact", "evidence-edge"]
    assert indicator["source_url"] == "https://example.test/evidence"
    assert indicator["simulated"] is True


@pytest.mark.asyncio
async def test_simulated_evidence_edge_is_visible_but_excluded_from_score():
    artifact = {
        "id": "artifact",
        "url": "https://example.test/evidence",
        "evidence_edge_id": "evidence-edge",
        "simulated": False,
        "evidence_simulated": True,
    }
    screen = {
        "predicate": "sanctions_screen",
        "result": "hit",
        "source": "screen",
        "confidence": 1.0,
        "retrieved_at": "2026-09-01",
        "status": "committed",
        "claim_id": "claim",
        "asserts_edge_id": "asserts-edge",
        "simulated": False,
        "artifact": artifact,
        "artifacts": [artifact],
    }
    risk = await risk_indicators("vendor", core(), {"supplies": []}, people(), [screen])
    indicator = next(i for i in risk["indicators"] if i["family"] == "sanctions")
    assert indicator["simulated"] is True
    assert indicator["element_ids"] == ["claim", "asserts-edge", "artifact", "evidence-edge"]

    contract = evaluate_risk_contract(core(), {"risk_evidence": []}, [screen], as_of=date(2026, 9, 8))
    sanctions = next(c for c in contract["categories"] if c["id"] == "sanctions_regulatory")
    assert sanctions["factors"] == []
    assert contract["score"] is None
    assert next(
        e for f in contract["diligence_flags"]
        if f["category"] == "sanctions_regulatory"
        for e in f["excluded_evidence"]
    )["simulated"] is True


@pytest.mark.asyncio
async def test_all_screen_artifacts_contribute_refs_and_simulation_provenance():
    screen = {
        "predicate": "adverse_media_screen",
        "result": "high",
        "source": "screen",
        "confidence": 0.8,
        "retrieved_at": "2026-09-02",
        "status": "committed",
        "claim_id": "claim",
        "asserts_edge_id": "asserts-edge",
        "simulated": False,
        "artifacts": [
            {
                "id": "real-artifact",
                "url": "https://example.test/real",
                "evidence_edge_id": "real-evidence-edge",
                "simulated": False,
                "evidence_simulated": False,
            },
            {
                "id": "scenario-artifact",
                "url": "https://example.test/scenario",
                "evidence_edge_id": "scenario-evidence-edge",
                "simulated": True,
                "evidence_simulated": False,
            },
        ],
    }
    screen["artifact"] = screen["artifacts"][0]
    risk = await risk_indicators("vendor", core(), {"supplies": []}, people(), [screen])
    indicator = next(i for i in risk["indicators"] if i["family"] == "media")
    assert indicator["simulated"] is True
    assert indicator["source_url"] == "https://example.test/real"
    assert indicator["element_ids"] == [
        "claim",
        "asserts-edge",
        "real-artifact",
        "real-evidence-edge",
        "scenario-artifact",
        "scenario-evidence-edge",
    ]

    contract = evaluate_risk_contract(core(), {"risk_evidence": []}, [screen], as_of=date(2026, 9, 8))
    media = next(c for c in contract["categories"] if c["id"] == "adverse_media")
    assert media["factors"] == []
    assert contract["score"] is None


@pytest.mark.asyncio
async def test_simulated_person_marks_only_people_indicator():
    ppl = {
        "current": [{
            "person_id": "person",
            "edge_id": "role-edge",
            "name": "Scenario Person",
            "title": "Director",
            "source": "scenario",
            "source_url": None,
            "simulated": True,
            "interlock": True,
            "formerly_elsewhere": False,
            "elsewhere": [{
                "entity_id": "other",
                "entity": "Other",
                "role_edge_id": "other-role-edge",
                "current": True,
                "flagged": False,
                "simulated": True,
                "source_url": "https://example.test/other-role",
            }],
        }],
        "former": [],
    }
    risk = await risk_indicators("vendor", core(), {"supplies": []}, ppl, [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "people")
    assert indicator["element_ids"] == ["person", "role-edge", "other", "other-role-edge"]
    assert indicator["source_url"] == "https://example.test/other-role"
    assert indicator["simulated"] is True
    assert next(i for i in risk["indicators"] if i["family"] == "ownership")["simulated"] is False


@pytest.mark.asyncio
async def test_parent_seat_indicator_carries_causal_location_and_relationship():
    data = core()
    data["parent_seat"] = {
        "id": "location",
        "code": "CN",
        "relationship_id": "seat-edge",
        "relationship_simulated": True,
        "source_url": "https://example.test/ownership",
    }
    risk = await risk_indicators("vendor", data, {"supplies": []}, people(), [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "ownership")
    assert indicator["element_ids"] == ["location", "seat-edge"]
    assert indicator["source_url"] == "https://example.test/ownership"
    assert indicator["simulated"] is True


@pytest.mark.asyncio
async def test_a_simulated_vendors_indicators_are_not_restamped():
    risk = await risk_indicators("vendor", core(simulated=True), {"supplies": []}, people(), [])
    assert not any(i["simulated"] for i in risk["indicators"])


@pytest.mark.asyncio
async def test_a_simulated_screen_scores_like_any_other(monkeypatch):
    artifact = {
        "id": "artifact",
        "evidence_edge_id": "evidence-edge",
        "evidence_simulated": True,
    }
    screen = {
        "predicate": "sanctions_screen",
        "result": "hit",
        "source": "screen",
        "confidence": 1.0,
        "retrieved_at": "2026-09-01",
        "status": "committed",
        "claim_id": "claim",
        "asserts_edge_id": "asserts-edge",
        "simulated": False,
        "artifact": artifact,
        "artifacts": [artifact],
    }
    monkeypatch.setattr(report_module, "entity_core", async_value(core()))
    monkeypatch.setattr(report_module, "supply_position", async_value({"supplies": [], "risk_evidence": []}))
    monkeypatch.setattr(report_module, "people", async_value(people()))
    monkeypatch.setattr(report_module, "screens", async_value([screen]))
    monkeypatch.setattr(report_module, "artifacts", async_value([]))
    monkeypatch.setattr(report_module, "news", async_value([]))

    report = await build_report("vendor")
    assert report is not None
    # Scenario evidence scores. The verified figure is kept alongside it for audit, and
    # the difference between the two is what the badge in the app bar stands for.
    assert report["risk"]["score"] == 100
    assert report["risk"]["includes_simulated"] is True
    assert report["risk"]["verified"]["score"] is None
    assert "composite" not in report["risk"]
    indicator = next(i for i in report["risk"]["indicators"] if i["family"] == "sanctions")
    assert indicator["simulated"] is True


@pytest.mark.asyncio
async def test_report_marks_graph_finding_with_simulated_backing_evidence(monkeypatch):
    display = {
        "id": "consumer",
        "edge_id": "supply-edge",
        "tier": 2,
        "sole_source": True,
        "contract_ref": "award",
        "source": "USAspending",
        "simulated": False,
    }
    backing = {
        "evidence_id": "supply-edge",
        "claim_id": "supply-claim",
        "contract_ref": "award",
        "sole_source": True,
        "status": "committed",
        "source": "USAspending",
        "retrieved_at": "2026-09-01",
        "confidence": 1.0,
        "artifact_simulated": False,
        "evidence_simulated": True,
    }
    monkeypatch.setattr(report_module, "entity_core", async_value(core()))
    monkeypatch.setattr(report_module, "supply_position", async_value({
        "supplies": [display],
        "risk_evidence": [backing],
    }))
    monkeypatch.setattr(report_module, "people", async_value(people()))
    monkeypatch.setattr(report_module, "screens", async_value([]))
    monkeypatch.setattr(report_module, "artifacts", async_value([]))
    monkeypatch.setattr(report_module, "news", async_value([]))

    report = await build_report("vendor")
    assert report is not None
    assert report["risk"]["score"] is None
    indicator = next(i for i in report["risk"]["indicators"] if i["family"] == "concentration")
    assert indicator["simulated"] is True


@pytest.mark.asyncio
async def test_report_marks_clear_concentration_with_simulated_backing_evidence(monkeypatch):
    display = {
        "id": "consumer",
        "edge_id": "supply-edge",
        "tier": 2,
        "sole_source": False,
        "contract_ref": "award",
        "source": "USAspending",
        "simulated": False,
    }
    backing = {
        "evidence_id": "supply-edge",
        "claim_id": "supply-claim",
        "contract_ref": "award",
        "sole_source": False,
        "status": "committed",
        "source": "USAspending",
        "retrieved_at": "2026-09-01",
        "confidence": 1.0,
        "evidence_simulated": True,
    }
    monkeypatch.setattr(report_module, "entity_core", async_value(core()))
    monkeypatch.setattr(report_module, "supply_position", async_value({
        "supplies": [display],
        "risk_evidence": [backing],
    }))
    monkeypatch.setattr(report_module, "people", async_value(people()))
    monkeypatch.setattr(report_module, "screens", async_value([]))
    monkeypatch.setattr(report_module, "artifacts", async_value([]))
    monkeypatch.setattr(report_module, "news", async_value([]))

    report = await build_report("vendor")
    assert report is not None
    assert report["risk"]["score"] is None
    indicator = next(i for i in report["risk"]["indicators"] if i["family"] == "concentration")
    assert indicator["severity"] == "clear"
    assert indicator["simulated"] is True
    assert indicator["element_ids"] == ["supply-edge", "supply-claim"]


@pytest.mark.asyncio
async def test_report_marks_clear_people_finding_from_simulated_roles(monkeypatch):
    simulated_people = {
        "current": [{
            "person_id": "scenario-person",
            "edge_id": "scenario-role",
            "name": "Scenario Director",
            "title": "Director",
            "source": "scenario",
            "source_url": "https://example.test/scenario-role",
            "simulated": False,
            "claim_id": "scenario-role-claim",
            "claim_simulated": False,
            "artifact_simulated": False,
            "evidence_simulated": True,
            "interlock": False,
            "formerly_elsewhere": False,
            "elsewhere": [],
        }],
        "former": [],
    }
    monkeypatch.setattr(report_module, "entity_core", async_value(core()))
    monkeypatch.setattr(report_module, "supply_position", async_value({"supplies": [], "risk_evidence": []}))
    monkeypatch.setattr(report_module, "people", async_value(simulated_people))
    monkeypatch.setattr(report_module, "screens", async_value([]))
    monkeypatch.setattr(report_module, "artifacts", async_value([]))
    monkeypatch.setattr(report_module, "news", async_value([]))

    report = await build_report("vendor")
    assert report is not None
    indicator = next(i for i in report["risk"]["indicators"] if i["family"] == "people")
    assert indicator["severity"] == "clear"
    assert indicator["simulated"] is True
    assert indicator["element_ids"] == ["scenario-person", "scenario-role", "scenario-role-claim"]
    assert indicator["source_url"] == "https://example.test/scenario-role"


@pytest.mark.asyncio
async def test_report_marks_unseated_parent_with_simulated_backing_evidence(monkeypatch):
    data = core()
    data["ultimate_parents"] = [{
        "id": "parent",
        "name": "Scenario Parent",
        "relationship_id": "parent-edge",
        "claim_id": "parent-claim",
        "simulated": False,
        "relationship_simulated": False,
        "claim_simulated": False,
        "artifact_simulated": False,
        "evidence_simulated": True,
        "source_url": "https://example.test/parent-evidence",
    }]
    monkeypatch.setattr(report_module, "entity_core", async_value(data))
    monkeypatch.setattr(report_module, "supply_position", async_value({"supplies": [], "risk_evidence": []}))
    monkeypatch.setattr(report_module, "people", async_value(people()))
    monkeypatch.setattr(report_module, "screens", async_value([]))
    monkeypatch.setattr(report_module, "artifacts", async_value([]))
    monkeypatch.setattr(report_module, "news", async_value([]))

    report = await build_report("vendor")
    assert report is not None
    indicator = next(i for i in report["risk"]["indicators"] if i["family"] == "ownership")
    assert indicator["simulated"] is True
    assert indicator["element_ids"] == ["parent", "parent-edge", "parent-claim"]
    assert indicator["source_url"] == "https://example.test/parent-evidence"

def _person_at_flagged(*, other_current: bool, person_current: bool = True) -> dict:
    person = {
        "person_id": "person", "edge_id": "role-edge", "claim_id": None,
        "name": "R. Ostrowski", "title": "Network Operations Engineer",
        "source": "scenario", "source_url": None, "simulated": False,
        "interlock": False, "formerly_elsewhere": False,
        "current": person_current,
        "elsewhere": [{
            "entity_id": "threat-group", "entity": "Obsidian Lantern",
            "role_edge_id": "affiliation-edge", "current": other_current,
            "flagged": True, "simulated": False, "supplier": False,
            "source_url": "https://example.test/threat-group",
        }],
    }
    person["moved_to_flagged"] = other_current and not person_current
    key = "current" if person_current else "former"
    return {"current": [], "former": [], key: [person]}


@pytest.mark.asyncio
async def test_a_current_employee_concurrently_inside_a_flagged_entity_is_a_high_finding():
    # The employer's own record is clean; the exposure is only reachable through the person.
    ppl = _person_at_flagged(other_current=True)
    risk = await risk_indicators("vendor", core(), {"supplies": []}, ppl, [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "people")
    assert indicator["severity"] == "high"
    assert "concurrently at flagged entity" in indicator["label"]
    assert "Obsidian Lantern" in indicator["label"]
    assert indicator["element_ids"] == ["person", "role-edge", "threat-group", "affiliation-edge"]


@pytest.mark.asyncio
async def test_a_lapsed_role_at_a_flagged_entity_stays_medium():
    ppl = _person_at_flagged(other_current=False)
    risk = await risk_indicators("vendor", core(), {"supplies": []}, ppl, [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "people")
    assert indicator["severity"] == "medium"
    assert "linked to flagged entity" in indicator["label"]


@pytest.mark.asyncio
async def test_a_former_employee_who_moved_to_a_flagged_entity_stays_medium():
    ppl = _person_at_flagged(other_current=True, person_current=False)
    risk = await risk_indicators("vendor", core(), {"supplies": []}, ppl, [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "people")
    assert indicator["severity"] == "medium"
    assert indicator["label"].startswith("Former")
