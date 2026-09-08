from datetime import date

from illuminate.report import RISK_CATEGORIES, approved_summary_findings, evaluate_risk_contract


AS_OF = date(2026, 9, 8)


def core(*, foreign=False):
    return {
        "e": {"id": "ent_fixture", "simulated": False},
        "parent_seat": {"code": "CN" if foreign else "US"},
        "parent_seat_evidence": [{
            "id": "edge_parent_seat",
            "seat_code": "CN" if foreign else "US",
            "source": "fixture",
            "retrieved_at": "2026-09-01",
            "confidence": 0.9,
            "status": "committed",
            "simulated": False,
        }],
        "ultimate_parents": [{"id": "ent_parent"}],
    }


def supply(*, sole=False):
    edge = {
            "sole_source": sole,
            "contract_ref": "award-1",
            "evidence_id": "edge_supply",
            "source": "fixture",
            "retrieved_at": "2026-09-01",
            "confidence": 0.9,
            "status": "committed",
            "simulated": False,
        }
    return {"supplies": [edge], "risk_evidence": [edge]}


def screen(category, result="clear", *, retrieved_at="2026-09-01", status="committed",
           simulated=False, confidence=0.9):
    predicate = RISK_CATEGORIES[category]["predicates"][0]
    return {
        "claim_id": f"clm_{category}",
        "predicate": predicate,
        "result": result,
        "source": "calibration-fixture",
        "confidence": confidence,
        "status": status,
        "simulated": simulated,
        "retrieved_at": retrieved_at,
        "artifact": {"id": f"art_{category}", "simulated": simulated},
        "artifacts": [{"id": f"art_{category}", "simulated": simulated}],
        "artifact_simulated": simulated,
        "detail": f"{category} fixture result",
    }


def all_screens(result="clear", **kwargs):
    return [screen(c, result, **kwargs) for c in RISK_CATEGORIES]


def test_trustworthy_fixture_is_low_risk_and_complete():
    result = evaluate_risk_contract(core(), supply(), all_screens(), as_of=AS_OF)
    assert result["contract_version"] == "uc11.vendor-risk.v1"
    assert result["score"] == 0
    assert result["band"] == "low"
    assert result["completeness"] == 1.0
    assert result["diligence_flags"] == []


def test_risky_fixture_has_fixed_weight_contributions_and_explanations():
    result = evaluate_risk_contract(
        core(foreign=True), supply(sole=True), all_screens("high"), as_of=AS_OF
    )
    assert result["score"] == 100
    assert result["band"] == "critical"
    assert result["disposition"] == "hold_and_escalate"
    for category in result["categories"]:
        for factor in category["factors"]:
            if category["contribution"]:
                assert factor["rule_id"]
                assert factor["evidence_refs"]
                assert factor["truth_status"] == "committed"


def test_incomplete_fixture_does_not_renormalize_available_risk():
    partial = [screen("cyber", "high")]
    result = evaluate_risk_contract(core(), {"supplies": [], "risk_evidence": []}, partial, as_of=AS_OF)
    assert result["score"] == 50
    assert result["band"] == "high"
    assert result["completeness"] == 0.286
    assert len([f for f in result["diligence_flags"] if f["code"] == "missing_approved_evidence"]) == 5


def test_stale_fixture_keeps_risk_but_flags_freshness():
    result = evaluate_risk_contract(
        core(), supply(), all_screens("medium", retrieved_at="2020-01-01"), as_of=AS_OF
    )
    assert result["score"] > 0
    assert result["freshness"] == "diligence_required"
    assert any(f["code"] == "stale_evidence" for f in result["diligence_flags"])


def test_repeated_fixture_projection_cannot_change_stale_graph_evidence():
    stale_supply = supply(sole=True)
    stale_supply["risk_evidence"][0]["retrieved_at"] = "2020-01-01"

    first = evaluate_risk_contract(core(), stale_supply, [], as_of=AS_OF)
    repeated = evaluate_risk_contract(core(), stale_supply, [], as_of=AS_OF)

    assert repeated == first
    supply_category = next(c for c in repeated["categories"] if c["id"] == "supply_criticality")
    assert supply_category["freshness"] == "stale"
    assert any(
        flag["category"] == "supply_criticality" and flag["code"] == "stale_evidence"
        for flag in repeated["diligence_flags"]
    )


def test_simulated_staged_and_rejected_evidence_never_scores_as_fact():
    excluded = [
        screen("cyber", "high", simulated=True),
        screen("legal", "high", status="staged"),
        screen("financial", "high", status="rejected"),
    ]
    result = evaluate_risk_contract(core(), supply(), excluded, as_of=AS_OF)
    assert result["score"] == 0
    assert result["completeness"] == 0.286
    legal = next(f for f in result["diligence_flags"] if f["category"] == "legal")
    assert legal["excluded_truth_statuses"] == ["staged"]


def test_all_missing_fixture_is_not_assessed_or_disposed_as_safe():
    result = evaluate_risk_contract(
        {"e": {"id": "ent_empty"}, "parent_seat": None, "parent_seat_evidence": []},
        {"supplies": [], "risk_evidence": []},
        [],
        as_of=AS_OF,
    )
    assert result["score"] is None
    assert result["band"] == "not_assessed"
    assert result["disposition"] == "complete_diligence"
    assert result["completeness"] == 0


def test_unknown_screen_result_and_zero_confidence_are_not_promoted():
    invalid = screen("legal", "unrecognized", confidence=0)
    valid = screen("cyber", "high", confidence=0)
    result = evaluate_risk_contract(core(), supply(), [invalid, valid], as_of=AS_OF)
    legal = next(c for c in result["categories"] if c["id"] == "legal")
    cyber = next(c for c in result["categories"] if c["id"] == "cyber")
    assert legal["severity"] is None
    assert cyber["confidence"] == 0
    assert result["confidence"] < 0.9


def test_stale_high_factor_is_not_masked_by_fresh_clear_factor():
    result = evaluate_risk_contract(
        core(), supply(), [
            screen("cyber", "high", retrieved_at="2020-01-01"),
            {**screen("cyber", "clear"), "claim_id": "clm_cyber_clear"},
        ],
        as_of=AS_OF,
    )
    cyber = next(c for c in result["categories"] if c["id"] == "cyber")
    assert cyber["severity"] == "high"
    assert cyber["freshness"] == "stale"


def test_simulated_graph_facts_are_excluded():
    simulated_core = core(foreign=True)
    simulated_core["parent_seat_evidence"][0]["simulated"] = True
    simulated_supply = supply(sole=True)
    simulated_supply["supplies"][0]["simulated"] = True
    result = evaluate_risk_contract(simulated_core, simulated_supply, [], as_of=AS_OF)
    assert result["score"] is None
    assert result["completeness"] == 0

def test_simulated_graph_evidence_relationships_are_excluded():
    simulated_core = core(foreign=True)
    simulated_core["parent_seat_evidence"][0]["evidence_simulated"] = True
    simulated_supply = supply(sole=True)
    simulated_supply["risk_evidence"][0]["evidence_simulated"] = True
    result = evaluate_risk_contract(simulated_core, simulated_supply, [], as_of=AS_OF)
    assert result["score"] is None
    assert result["completeness"] == 0
def test_rejected_backing_claim_and_unknown_supply_value_are_excluded():
    rejected_core = core(foreign=True)
    rejected_core["parent_seat_evidence"][0].update({
        "claim_id": "clm_parent",
        "claim_status": "rejected",
    })
    unknown_supply = supply()
    unknown_supply["risk_evidence"][0]["sole_source"] = None
    result = evaluate_risk_contract(rejected_core, unknown_supply, [], as_of=AS_OF)
    assert result["score"] is None
    assert result["completeness"] == 0


def test_all_supply_evidence_participates_beyond_display_rows():
    data = supply()
    data["supplies"] = []  # The display page is independent from scoring evidence.
    stale_sole = {**data["risk_evidence"][0], "evidence_id": "edge_hidden",
                  "sole_source": True, "retrieved_at": "2020-01-01"}
    data["risk_evidence"].append(stale_sole)
    result = evaluate_risk_contract(
        {"e": {"id": "ent_empty"}, "parent_seat": None, "parent_seat_evidence": []},
        data,
        [],
        as_of=AS_OF,
    )
    category = next(c for c in result["categories"] if c["id"] == "supply_criticality")
    assert category["severity"] == "medium"
    assert category["freshness"] == "stale"
    assert len(category["factors"]) == 2


def test_all_parent_seats_participate_regardless_of_display_projection():
    data = core()
    data["parent_seat"] = {"code": "US"}
    data["parent_seat_evidence"].append({
        **data["parent_seat_evidence"][0],
        "id": "edge_foreign_parent",
        "seat_code": "CN",
    })
    result = evaluate_risk_contract(data, {"supplies": [], "risk_evidence": []}, [], as_of=AS_OF)
    ownership = next(c for c in result["categories"] if c["id"] == "ownership")
    assert ownership["severity"] == "high"
    assert len(ownership["factors"]) == 2


def test_any_simulated_artifact_excludes_the_screen_claim():
    item = screen("cyber", "high")
    item["artifacts"].append({"id": "art_simulated", "simulated": True})
    item["artifact_simulated"] = True
    result = evaluate_risk_contract(
        {"e": {"id": "ent_empty"}, "parent_seat": None, "parent_seat_evidence": []},
        {"supplies": [], "risk_evidence": []},
        [item],
        as_of=AS_OF,
    )
    assert result["score"] is None
    assert result["completeness"] == 0


def test_legacy_singular_simulated_artifact_is_also_excluded():
    item = screen("cyber", "high")
    item.pop("artifacts")
    item.pop("artifact_simulated")
    item["artifact"]["simulated"] = True
    result = evaluate_risk_contract(
        {"e": {"id": "ent_empty"}, "parent_seat": None, "parent_seat_evidence": []},
        {"supplies": [], "risk_evidence": []},
        [item],
        as_of=AS_OF,
    )
    assert result["score"] is None


def test_real_screen_claims_on_simulated_subject_are_excluded():
    simulated_core = core(foreign=True)
    simulated_core["e"]["simulated"] = True
    result = evaluate_risk_contract(
        simulated_core,
        supply(sole=True),
        all_screens("high"),
        as_of=AS_OF,
    )
    assert result["score"] is None
    assert result["band"] == "not_assessed"
    assert result["completeness"] == 0
    assert all(
        evidence["simulated"]
        for flag in result["diligence_flags"]
        for evidence in flag.get("excluded_evidence", [])
    )


def test_summary_projection_excludes_rejected_backing_claims():
    rejected_core = core(foreign=True)
    rejected_core["parent_seat_evidence"][0].update({
        "claim_id": "clm_parent",
        "claim_status": "rejected",
    })
    risk = evaluate_risk_contract(
        rejected_core,
        {"supplies": [], "risk_evidence": []},
        [],
        as_of=AS_OF,
    )

    findings = approved_summary_findings({
        "identity": {"id": "ent_fixture", "name": "Fixture", "simulated": False},
        "risk": risk,
    })
    ownership = next(f for f in findings if f["family"] == "ownership")

    assert ownership["no_data"] is True
    assert ownership["severity"] is None
    assert ownership["evidence_ids"] == []


def test_summary_projection_excludes_simulated_evidence_but_keeps_real_refs():
    simulated = screen("cyber", "high", simulated=True)
    committed = screen("legal", "medium")
    risk = evaluate_risk_contract(
        {"e": {"id": "ent_fixture", "simulated": False}, "parent_seat": None, "parent_seat_evidence": []},
        {"supplies": [], "risk_evidence": []},
        [simulated, committed],
        as_of=AS_OF,
    )

    findings = approved_summary_findings({
        "identity": {"id": "ent_fixture", "name": "Fixture", "simulated": False},
        "risk": risk,
    })
    cyber = next(f for f in findings if f["family"] == "cyber")
    legal = next(f for f in findings if f["family"] == "legal")

    assert cyber["no_data"] is True
    assert cyber["evidence_ids"] == []
    assert legal["severity"] == "medium"
    assert legal["evidence_ids"] == ["art_legal", "clm_legal"]
