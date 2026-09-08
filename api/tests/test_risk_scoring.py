"""How a node's risk score is put together.

Every dimension is graded from a plain dict, so these tests reach no graph. The one thing
they are really guarding is the rule that a signal which returned no data is not a zero:
a score built out of silence is the failure mode that makes a screening tool dangerous,
and several of these tests exist only to keep that from creeping back in.
"""
from __future__ import annotations

import pytest

from illuminate import risk, riskdata
from illuminate.connectors import section_1260h
from illuminate.connectors.edgar import grade_filings

TODAY = risk.date(2026, 9, 8)


def entity(**over) -> dict:
    base = {
        "id": "ent_vendor", "name": "Vendor", "kind": "organization", "flagged": False, "flag_reason": None,
        "registration_status": None, "registration_expires": None, "entity_status": None, "public": False,
        "ticker": None, "market_cap": None, "price_change_12m": None, "revenue": None,
        "incorporated": [], "parent_seat": [], "operates": [], "manufactures": [],
        "consumers": 0, "sole_source_ids": [], "docs": [],
    }
    return {**base, **over}


def screen(predicate: str, result: str, **over) -> dict:
    return {"predicate": predicate, "result": result, "source": "OFAC", "detail": "detail",
            "retrieved_at": "2026-09-01T00:00:00Z", "url": None, **over}


# --- no data is not a zero ---------------------------------------------------------

def test_a_dimension_with_nothing_to_go_on_says_so_instead_of_scoring_clear():
    comp = risk._designation(entity(), {})
    assert comp["no_data"] is True and comp["severity"] is None


def test_an_unscreened_unplaced_private_entity_gets_no_score_at_all():
    # Nothing is known about it, so it is unscored — not a reassuring low number.
    comps = [
        risk._designation(entity(), {}),
        risk._proximity_component(entity(), None),
        risk._foreign(entity(), []),
        risk._financial(entity(), {}, TODAY),
        risk._regional(entity()),
        risk._concentration(entity()),
        risk._media({}),
    ]
    # Proximity is the exception: "nothing designated within reach" is a real finding.
    scored = [c for c in comps if not c["no_data"]]
    assert [c["family"] for c in scored] == ["proximity"]
    value, _ = risk.composite(comps)
    assert value == 0 and risk.band(value) == "low"


def test_the_composite_ignores_absent_dimensions_rather_than_averaging_them_in():
    designated = risk._designation(entity(), {"sanctions_screen": screen("sanctions_screen", "hit")})
    quiet = risk._regional(entity())
    assert quiet["no_data"] is True
    # One dimension answered, and it answered "high": the score is high, not diluted to a
    # seventh of high by six silent dimensions.
    value, scored = risk.composite([designated, quiet])
    assert value == 100 and len(scored) == 1
    assert risk.band(value) == "severe"


def test_a_node_with_no_data_anywhere_has_no_score():
    value, scored = risk.composite([risk._designation(entity(), {}), risk._regional(entity())])
    assert value is None and scored == []
    assert risk.band(None) is None


# --- designation -------------------------------------------------------------------

def test_a_screen_hit_is_the_finding_and_names_its_lists():
    comp = risk._designation(entity(), {
        "sanctions_screen": screen("sanctions_screen", "hit", source="OFAC"),
        "restricted_list_screen": screen("restricted_list_screen", "hit", source="U.S. Department of Defense"),
    })
    assert comp["severity"] == "high"
    assert "OFAC" in comp["label"] and "Department of Defense" in comp["label"]


def test_a_node_flagged_without_a_screen_behind_it_still_counts_as_designated():
    comp = risk._designation(entity(flagged=True, flag_reason="designated cyber-threat group"), {})
    assert comp["severity"] == "high" and "cyber-threat" in comp["detail"]


def test_screens_that_ran_and_found_nothing_grade_clear_and_say_how_many_ran():
    comp = risk._designation(entity(), {
        "sanctions_screen": screen("sanctions_screen", "clear"),
        "exclusion_screen": screen("exclusion_screen", "clear", source="SAM.gov"),
    })
    assert comp["severity"] == "clear" and "2 lists" in comp["label"]


# --- proximity ---------------------------------------------------------------------

@pytest.mark.parametrize("hops,severity", [(1, "high"), (2, "medium"), (3, "low")])
def test_severity_falls_off_with_each_degree_of_separation(hops, severity):
    near = {"seed": "Obsidian Lantern", "hops": hops, "chain": ["Vendor", "Obsidian Lantern"],
            "node_ids": ["ent_vendor", "ent_group"], "rel_ids": ["rel_1"], "reachable": 1}
    comp = risk._proximity_component(entity(), near)
    assert comp["severity"] == severity
    assert f"{hops} degree" in comp["label"] and "Obsidian Lantern" in comp["label"]


def test_the_walk_that_produced_the_finding_travels_with_it():
    # The canvas has to be able to light up the route, or the score is an assertion the
    # user cannot check.
    near = {"seed": "Obsidian Lantern", "hops": 2, "chain": ["Vendor", "R. Ostrowski", "Obsidian Lantern"],
            "node_ids": ["ent_vendor", "per_ostrowski", "ent_group"], "rel_ids": ["rel_role", "rel_affil"],
            "reachable": 1}
    comp = risk._proximity_component(entity(), near)
    assert comp["element_ids"] == ["ent_vendor", "per_ostrowski", "ent_group", "rel_role", "rel_affil"]
    assert "Vendor → R. Ostrowski → Obsidian Lantern" in comp["detail"]


def test_further_designated_parties_within_reach_are_counted_in_the_detail():
    near = {"seed": "A", "hops": 1, "chain": ["V", "A"], "node_ids": [], "rel_ids": [], "reachable": 3}
    assert "2 further designated parties" in risk._proximity_component(entity(), near)["detail"]


def test_nothing_designated_within_reach_is_a_clear_finding_not_a_missing_one():
    comp = risk._proximity_component(entity(), None)
    assert comp["severity"] == "clear" and comp["no_data"] is False


# --- foreign ownership and operations ----------------------------------------------

def test_a_delaware_shell_that_manufactures_in_a_covered_nation_is_graded_on_the_plant():
    # The scenario's shape: incorporation looks domestic and answers nothing.
    comp = risk._foreign(entity(incorporated=["US-DE"], manufactures=["CN"]), [])
    assert comp["severity"] == "high"
    assert "CN" in comp["label"] and "covered nation" in comp["label"]


def test_an_ultimate_parent_seated_abroad_is_read_even_when_the_entity_is_domestic():
    comp = risk._foreign(entity(incorporated=["US"]), [{"id": "ent_zj", "name": "Zhejiang", "code": "CN", "hops": 2, "rel_ids": []}])
    assert comp["severity"] == "high" and "ent_zj" in comp["element_ids"]


def test_a_chain_through_a_non_disclosing_registry_is_medium_and_says_why():
    comp = risk._foreign(entity(incorporated=["US"], parent_seat=["HK"]), [])
    assert comp["severity"] == "medium"
    assert "HK" in comp["label"] and "cannot be walked to its end" in comp["detail"]


def test_domestic_and_allied_throughout_grades_clear():
    comp = risk._foreign(entity(incorporated=["US"], operates=["US", "GB"]), [])
    assert comp["severity"] == "clear" and "Domestic or allied" in comp["label"]


def test_an_entity_with_no_resolved_jurisdiction_is_not_graded_at_all():
    assert risk._foreign(entity(), [])["no_data"] is True


def test_an_unclassified_country_code_does_not_quietly_grade_as_safe():
    # 'ZZ' is in no table; the dimension must abstain rather than call it clear.
    assert risk._foreign(entity(incorporated=["ZZ"]), [])["no_data"] is True


# --- regional conflict and natural hazard ------------------------------------------

def test_a_plant_in_an_active_conflict_zone_is_high():
    comp = risk._regional(entity(manufactures=["UA"]))
    assert comp["severity"] == "high" and "conflict" in comp["label"]


def test_the_same_conflict_zone_is_a_step_lower_when_only_an_office_sits_there():
    assert risk._regional(entity(operates=["UA"]))["severity"] == "medium"


def test_natural_hazard_exposure_grades_below_armed_conflict():
    assert risk._regional(entity(manufactures=["PH"]))["severity"] == "medium"
    assert risk._regional(entity(operates=["PH"]))["severity"] == "low"


def test_incorporation_is_ignored_because_a_hurricane_does_not_read_the_paperwork():
    assert risk._regional(entity(incorporated=["PH"]))["no_data"] is True


def test_a_us_state_resolves_against_the_state_table_not_the_country():
    assert riskdata.hazard_level("US-FL") == "high"
    assert riskdata.hazard_level("US-VT") == "low"
    assert riskdata.hazard_level("US") == "medium"


def test_a_country_with_no_hazard_reference_records_no_data_and_names_the_snapshot():
    comp = risk._regional(entity(manufactures=["ZZ"]))
    assert comp["no_data"] is True and riskdata.AS_OF in comp["detail"]


# --- financial distress -------------------------------------------------------------

def test_an_expired_registration_is_a_high_distress_signal():
    comp = risk._financial(entity(registration_expires="2025-01-01"), {}, TODAY)
    assert comp["severity"] == "high" and "expired" in comp["detail"]


def test_a_registration_about_to_lapse_is_only_a_low_one():
    comp = risk._financial(entity(registration_expires="2026-10-01"), {}, TODAY)
    assert comp["severity"] == "low"


def test_a_late_filing_notification_and_a_collapsed_market_value_both_register():
    comp = risk._financial(entity(public=True, price_change_12m=-60, docs=[{"kind": "filing", "form": "NT 10-K", "at": "2026-05-01"}]), {}, TODAY)
    assert comp["severity"] == "high"
    assert "NT 10-K" in comp["detail"] and "down 60%" in comp["detail"]
    assert comp["label"] == "2 distress signals"


def test_a_listed_company_that_has_stopped_filing_is_a_signal_in_itself():
    comp = risk._financial(entity(public=True, docs=[{"kind": "filing", "form": "10-K", "at": "2024-01-01"}]), {}, TODAY)
    assert comp["severity"] == "medium" and "nothing filed since" in comp["detail"]


def test_a_private_entity_with_no_filings_and_no_registration_is_not_graded():
    comp = risk._financial(entity(), {}, TODAY)
    assert comp["no_data"] is True


def test_an_active_registration_grades_continuity_and_says_it_is_not_solvency():
    comp = risk._financial(entity(registration_status="Active"), {}, TODAY)
    assert comp["severity"] == "clear" and "not solvency" in comp["detail"]


# --- people ------------------------------------------------------------------------

def _person(**over) -> dict:
    return {"id": "per_x", "name": "R. Ostrowski", "flagged": False, "flag_reason": None,
            "public_official": False, "roles": [], **over}


def test_a_persons_jurisdiction_exposure_comes_from_their_seats_not_their_name():
    entities = {"ent_a": entity(id="ent_a", name="Ningbo Precision", incorporated=["CN"])}
    comp = risk._person_foreign(_person(roles=[{"id": "ent_a", "name": "Ningbo Precision", "current": True}]), entities, {})
    assert comp["severity"] == "high" and "Holds a seat" in comp["label"]


def test_a_lapsed_seat_is_still_read_but_in_the_past_tense():
    entities = {"ent_a": entity(id="ent_a", name="Ningbo Precision", incorporated=["CN"])}
    comp = risk._person_foreign(_person(roles=[{"id": "ent_a", "name": "Ningbo Precision", "current": False}]), entities, {})
    assert comp["severity"] == "high" and comp["label"].startswith("Held")


def test_a_person_with_no_placed_seats_is_not_graded_on_jurisdiction():
    assert risk._person_foreign(_person(), {}, {})["no_data"] is True


# --- bands and weighting -------------------------------------------------------------

@pytest.mark.parametrize("score,expected", [(100, "severe"), (75, "severe"), (74, "high"), (50, "high"),
                                            (49, "elevated"), (25, "elevated"), (24, "low"), (0, "low")])
def test_band_thresholds(score, expected):
    assert risk.band(score) == expected


def test_designation_outweighs_the_softer_dimensions_it_competes_with():
    # A designated vendor that is otherwise spotless still scores above a clean one that
    # merely operates somewhere hazardous.
    designated = risk.composite([
        risk._designation(entity(flagged=True), {}),
        risk._regional(entity(operates=["US-VT"])),
        risk._concentration(entity(consumers=2)),
    ])[0]
    hazardous = risk.composite([
        risk._designation(entity(), {"sanctions_screen": screen("sanctions_screen", "clear")}),
        risk._regional(entity(manufactures=["PH"])),
        risk._concentration(entity(consumers=2)),
    ])[0]
    assert designated > hazardous


def test_confidence_reports_how_much_of_the_model_actually_answered():
    comps = [risk._designation(entity(flagged=True), {}), risk._regional(entity())]
    # Designation carries weight 3.0 of the 4.0 offered here; regional said nothing.
    assert risk.confidence(comps) == 75
    assert risk.confidence([risk._regional(entity())]) == 0


def test_a_thin_score_is_still_reported_but_the_note_says_not_to_act_on_it_yet():
    row = entity(id="ent_thin", name="Pacific Alloy Holdings")
    near = {"seed": "Ningbo", "hops": 1, "chain": ["Ningbo", "Pacific Alloy"], "node_ids": [], "rel_ids": [], "reachable": 1}
    scored = risk._score([
        risk._designation(row, {}), risk._proximity_component(row, near), risk._foreign(row, []),
        risk._financial(row, {}, TODAY), risk._regional(row), risk._concentration(row), risk._media({}),
    ], row, "Entity")
    # Everything known about it is bad, so it scores 100 — but on a fifth of the model,
    # and the note has to carry that or the number lies about how much is behind it.
    assert scored["score"] == 100 and scored["band"] == "severe"
    assert scored["confidence"] < 30
    assert "raise the confidence before acting" in scored["note"]
    # The note names the dimensions that went missing, so "why is this thin" is answerable
    # without opening the breakdown.
    assert "Not yet screened against any designation list" in scored["note"]


def test_full_coverage_does_not_carry_the_act_with_caution_warning():
    row = entity(registration_status="Active", incorporated=["US"], operates=["US-VT"], consumers=2,
                 manufactures=["US-VT"])
    scored = risk._score([
        risk._designation(row, {"sanctions_screen": screen("sanctions_screen", "clear")}),
        risk._proximity_component(row, None), risk._foreign(row, []), risk._financial(row, {}, TODAY),
        risk._regional(row), risk._concentration(row),
        risk._media({"adverse_media_screen": screen("adverse_media_screen", "clear")}),
    ], row, "Entity")
    assert scored["confidence"] == 100 and "raise the confidence" not in scored["note"]


def test_every_dimension_the_scorer_emits_has_a_declared_weight():
    for name in ("designation", "proximity", "foreign", "financial", "regional", "concentration", "media"):
        assert name in risk.DIMENSIONS


# --- the §1260H roster ---------------------------------------------------------------

def test_the_1260h_screen_matches_a_designation_through_its_trading_name():
    res = section_1260h.screen("Huawei Investment & Holding Co., Ltd.")
    assert res["result"] == "hit" and res["hits"][0]["name"] == "Huawei Technologies"


def test_an_unrelated_company_does_not_match():
    assert section_1260h.screen("Bell Textron Inc.")["result"] == "clear"


def test_a_clear_result_discloses_that_the_committed_roster_is_an_excerpt():
    # A clear screen against a partial list is not a clearance, and has to say so.
    res = section_1260h.screen("Bell Textron Inc.")
    assert res["complete"] is False
    assert "not the full annex" in section_1260h.describe(res)


def test_a_hit_names_what_it_matched_so_an_analyst_can_confirm_it():
    detail = section_1260h.describe(section_1260h.screen("AVIC"))
    assert "Aviation Industry Corporation of China" in detail and "matched" in detail


# --- EDGAR filing behaviour ----------------------------------------------------------

def test_a_late_filing_notification_grades_medium():
    result, detail = grade_filings([("NT 10-K", "2026-04-01"), ("10-K", "2026-06-01")], attached=2)
    assert result == "medium" and "late-filing notification" in detail


def test_a_company_filing_annuals_on_time_grades_clear():
    result, detail = grade_filings([("10-K", "2026-02-01"), ("10-Q", "2026-05-01")], attached=2)
    assert result == "clear" and "no financial-statement analysis" in detail


def test_no_annual_report_in_the_index_is_a_low_signal_not_a_clear_one():
    result, _ = grade_filings([("8-K", "2026-02-01")], attached=1)
    assert result == "low"


# --- reference data ------------------------------------------------------------------

def test_the_covered_nations_are_the_statutory_four():
    assert set(riskdata.COVERED_NATIONS) == {"CN", "RU", "KP", "IR"}
    for code in riskdata.COVERED_NATIONS:
        assert riskdata.JURISDICTION_CLASS[code] == "covered"


def test_every_jurisdiction_class_has_a_severity_and_a_label():
    for cls in set(riskdata.JURISDICTION_CLASS.values()):
        assert cls in riskdata.CLASS_SEVERITY and cls in riskdata.CLASS_LABEL
        assert riskdata.CLASS_SEVERITY[cls] in risk.SEVERITY_WEIGHT


def test_the_reference_note_dates_the_snapshot():
    assert riskdata.AS_OF in riskdata.refresh_note()
    assert "no-data, not as clear" in riskdata.refresh_note()
