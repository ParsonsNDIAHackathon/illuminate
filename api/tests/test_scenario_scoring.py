"""Scenario material has to be able to move a score, or planting it proves nothing.

The verified evaluation still refuses to score it — that is what keeps an exported finding
about a real company honest — so both evaluations are checked here. No test in this module
connects to Neo4j.
"""
from __future__ import annotations

from datetime import date

import pytest

from illuminate.report import RISK_CATEGORIES, evaluate_risk_contract

AS_OF = date(2026, 9, 8)


def core(simulated: bool = False) -> dict:
    return {"e": {"id": "vendor", "name": "Vendor", "simulated": simulated},
            "parent_seat": None, "parent_seat_evidence": [], "ultimate_parents": []}


def supply() -> dict:
    return {"supplies": [], "risk_evidence": []}


def screen(*, simulated: bool) -> dict:
    return {
        "claim_id": "claim-cyber", "predicate": "cyber_screen", "result": "hit",
        "status": "committed", "simulated": simulated, "artifacts": [],
        "source": "scenario threat reporting", "retrieved_at": "2026-09-08T00:00:00Z",
        "confidence": 0.9, "method": "simulated",
    }


def insider(*, simulated: bool, other_current: bool = True) -> dict:
    person = {
        "person_id": "person", "edge_id": "role-edge", "claim_id": None, "name": "R. Ostrowski",
        "title": "Network Operations Engineer", "current": True, "simulated": simulated,
        "source": "scenario", "retrieved_at": "2026-09-08T00:00:00Z", "confidence": 1.0,
        "status": "committed", "method": "simulated", "interlock": False, "formerly_elsewhere": False,
        "moved_to_flagged": False,
        "elsewhere": [{
            "entity_id": "threat-group", "entity": "Obsidian Lantern", "role_edge_id": "affiliation-edge",
            "current": other_current, "flagged": True, "simulated": simulated, "supplier": False,
            "source": "scenario", "retrieved_at": "2026-09-08T00:00:00Z", "confidence": 1.0,
            "status": "committed", "method": "simulated",
        }],
    }
    return {"current": [person], "former": []}


def category(result: dict, name: str) -> dict:
    return next(c for c in result["categories"] if c["id"] == name)


def test_the_verified_evaluation_still_refuses_simulated_evidence():
    result = evaluate_risk_contract(core(), supply(), [screen(simulated=True)], as_of=AS_OF)
    assert result["score"] == 0 or result["score"] is None
    assert category(result, "cyber")["severity"] is None
    assert result["policy"]["simulated_evidence_scores"] is False


def test_the_scenario_evaluation_scores_the_same_evidence():
    result = evaluate_risk_contract(core(), supply(), [screen(simulated=True)], as_of=AS_OF, include_simulated=True)
    assert category(result, "cyber")["severity"] == "high"
    assert result["score"] == 100
    assert result["policy"]["simulated_evidence_scores"] is True


def test_a_simulated_entity_is_scoreable_in_scenario_mode_only():
    screens = [screen(simulated=False)]
    verified = evaluate_risk_contract(core(simulated=True), supply(), screens, as_of=AS_OF)
    scenario = evaluate_risk_contract(core(simulated=True), supply(), screens, as_of=AS_OF, include_simulated=True)
    assert category(verified, "cyber")["severity"] is None
    assert category(scenario, "cyber")["severity"] == "high"


def test_personnel_is_a_scored_category():
    # Without it an insider tie was a visible indicator that contributed nothing.
    assert "personnel" in RISK_CATEGORIES


def test_an_insider_inside_a_flagged_entity_moves_the_vendors_score():
    ppl = insider(simulated=True)
    verified = evaluate_risk_contract(core(), supply(), [], as_of=AS_OF, people_data=ppl)
    scenario = evaluate_risk_contract(core(), supply(), [], as_of=AS_OF, people_data=ppl, include_simulated=True)
    assert category(verified, "personnel")["severity"] is None
    assert verified["score"] is None
    found = category(scenario, "personnel")
    assert found["severity"] == "high"
    assert scenario["score"] == 100
    assert found["factors"][0]["rule_id"] == "personnel.flagged-affiliation.v1"
    assert "concurrently" in found["factors"][0]["explanation"]


def test_a_lapsed_tie_scores_lower_than_a_concurrent_one():
    lapsed = evaluate_risk_contract(core(), supply(), [], as_of=AS_OF,
                                    people_data=insider(simulated=True, other_current=False), include_simulated=True)
    assert category(lapsed, "personnel")["severity"] == "medium"


def test_a_real_insider_tie_scores_without_any_scenario_switch():
    # The category is not a demo prop: unsimulated evidence of the same shape scores verified.
    result = evaluate_risk_contract(core(), supply(), [], as_of=AS_OF, people_data=insider(simulated=False))
    assert category(result, "personnel")["severity"] == "high"


def test_an_unflagged_colleague_is_not_a_finding():
    ppl = insider(simulated=True)
    ppl["current"][0]["elsewhere"][0]["flagged"] = False
    result = evaluate_risk_contract(core(), supply(), [], as_of=AS_OF, people_data=ppl, include_simulated=True)
    assert category(result, "personnel")["severity"] is None


def test_the_factor_carries_the_ids_needed_to_highlight_the_path():
    result = evaluate_risk_contract(core(), supply(), [], as_of=AS_OF,
                                    people_data=insider(simulated=True), include_simulated=True)
    refs = category(result, "personnel")["factors"][0]["evidence_refs"]
    assert refs == ["role-edge", "affiliation-edge", "threat-group"]
