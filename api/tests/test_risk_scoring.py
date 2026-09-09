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
        "docs": [],
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
        risk._dependency(entity(), [], {}),
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


# --- proximity is asymmetric ---------------------------------------------------------
#
# Buying from a designated party puts its problem inside your product. Selling to one is a
# concern of a different kind and a smaller one, so the same number of hops grades softer
# when the only route runs against the flow of supply.


def reach(hops: int, seed: str = "Obsidian Lantern") -> dict:
    return {"seed": seed, "hops": hops, "chain": ["A", "B"], "node_ids": ["ent_a"],
            "rel_ids": ["rel_1"], "reachable": 1}


def test_a_designated_supplier_outweighs_a_designated_customer_at_the_same_distance():
    downstream = risk.merge_proximity({"ent_x": reach(1)}, {"ent_x": reach(1)})["ent_x"]
    reverse = risk.merge_proximity({}, {"ent_x": reach(1)})["ent_x"]
    assert downstream["severity"] == "high" and downstream["downstream"] is True
    assert reverse["severity"] == "medium" and reverse["downstream"] is False
    assert risk.SEVERITY_WEIGHT[downstream["severity"]] > risk.SEVERITY_WEIGHT[reverse["severity"]]


def test_a_distant_customer_of_a_designated_party_is_not_a_finding_at_all():
    # Three hops upstream of a designated buyer softens from low to clear.
    assert risk.merge_proximity({}, {"ent_x": reach(3)})["ent_x"]["severity"] == "clear"


def test_the_worse_of_the_two_readings_wins():
    # One hop the wrong way (→ medium) beats three hops the right way (→ low): the
    # asymmetry must not be able to hide a close reverse tie.
    merged = risk.merge_proximity({"ent_x": reach(3)}, {"ent_x": reach(1)})["ent_x"]
    assert merged["severity"] == "medium" and merged["downstream"] is False


def test_a_reverse_route_says_so_in_the_finding_it_produces():
    comp = risk._proximity_component(entity(), risk.merge_proximity({}, {"ent_x": reach(1)})["ent_x"])
    assert "downstream of it" in comp["label"]
    assert "against the flow of supply" in comp["detail"]


def test_control_and_personnel_ties_are_walked_in_both_directions():
    # Owning a designated subsidiary and being owned by a designated parent are both
    # severe, and a shared officer has no direction to speak of.
    for rel in ("OWNS", "ULTIMATE_PARENT_OF", "BENEFICIAL_OWNER_OF", "HELD_ROLE", "MEMBER_OF", "TRANSACTS_WITH"):
        assert f"{rel}>" not in risk.PROXIMITY_RELS_DOWNSTREAM
        assert rel in risk.PROXIMITY_RELS_DOWNSTREAM
    # Supply is the one that carries a direction.
    assert "SUPPLIES>" in risk.PROXIMITY_RELS_DOWNSTREAM
    assert "SUPPLIES>" not in risk.PROXIMITY_RELS_ANY


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


# --- dependence on suppliers ---------------------------------------------------------
#
# The rule these guard: being a sole source is not a risk the *supplier* carries. It says
# nothing about whether that company will fail or be designated. It is a risk its customer
# carries, in proportion to how irreplaceable the supplier is.


def supply_edge(supplier: str, name: str, *, sole: bool = False, amount: float = 0) -> dict:
    return {"consumer": "ent_vendor", "supplier": supplier, "supplier_name": name,
            "edge_id": f"rel_{supplier}", "sole_source": sole, "amount": amount}


def test_being_a_sole_source_adds_nothing_to_the_suppliers_own_score():
    # The supplier's dimensions are exactly what they would be without the award; there is
    # no dimension on this side of the edge for sole-source status to move.
    assert "concentration" not in risk.DIMENSIONS
    supplier = entity(id="ent_sole", name="Only Option")
    comps = [
        risk._designation(supplier, {"sanctions_screen": screen("sanctions_screen", "clear")}),
        risk._proximity_component(supplier, None),
        risk._dependency(supplier, [], {}),
    ]
    assert risk.composite(comps)[0] == 0


def test_a_sole_source_hands_its_customer_the_whole_of_its_risk():
    weighted = risk.dependence_weights([supply_edge("ent_a", "Only Option", sole=True)])
    comp = risk._dependency(entity(), weighted, {"ent_a": 80})
    assert comp["severity"] == "high"
    assert "Sole-source dependence on Only Option" in comp["label"]
    assert "Exposure 80/100" in comp["detail"]


def test_the_same_supplier_among_four_competed_ones_is_a_quarter_of_the_problem():
    edges = [supply_edge("ent_a", "Alpha"), supply_edge("ent_b", "Bravo"),
             supply_edge("ent_c", "Charlie"), supply_edge("ent_d", "Delta")]
    comp = risk._dependency(entity(), risk.dependence_weights(edges), {"ent_a": 80, "ent_b": 0, "ent_c": 0, "ent_d": 0})
    # 80 × 0.25 = 20: still worth seeing, nothing like a single point of failure.
    assert comp["severity"] == "low"
    assert "Exposure 20/100" in comp["detail"]


def test_a_diversified_base_of_equally_risky_suppliers_is_not_diluted_away():
    # Dilution is about substitutability, not about arithmetic comfort: if every option is
    # as bad as the last, switching supplier buys nothing and the exposure is undiminished.
    edges = [supply_edge(f"ent_{i}", f"S{i}") for i in range(4)]
    comp = risk._dependency(entity(), risk.dependence_weights(edges), {f"ent_{i}": 80 for i in range(4)})
    assert comp["severity"] == "high"
    assert "Exposure 80/100" in comp["detail"]


def test_dependence_is_split_by_obligated_amount_when_the_awards_say_so():
    edges = [supply_edge("ent_big", "Big", amount=900), supply_edge("ent_small", "Small", amount=100)]
    weights = dict((e["supplier"], w) for e, w in risk.dependence_weights(edges))
    assert weights["ent_big"] == pytest.approx(0.9)
    assert weights["ent_small"] == pytest.approx(0.1)


def test_missing_amounts_fall_back_to_an_even_split_rather_than_dropping_a_supplier():
    edges = [supply_edge("ent_a", "Alpha"), supply_edge("ent_b", "Bravo")]
    weights = dict((e["supplier"], w) for e, w in risk.dependence_weights(edges))
    assert weights == pytest.approx({"ent_a": 0.5, "ent_b": 0.5})


def test_each_sole_source_carries_its_own_full_weight_alongside_competed_ones():
    edges = [supply_edge("ent_sole", "Irreplaceable", sole=True),
             supply_edge("ent_a", "Alpha"), supply_edge("ent_b", "Bravo")]
    weights = dict((e["supplier"], w) for e, w in risk.dependence_weights(edges))
    # The competed pair shares one unit between them; the sole source is not part of that
    # bargain, because nothing else was competed for its scope.
    assert weights == pytest.approx({"ent_sole": 1.0, "ent_a": 0.5, "ent_b": 0.5})


def test_a_single_competed_supplier_is_still_a_single_point_of_dependence():
    weighted = risk.dependence_weights([supply_edge("ent_a", "Alpha")])
    assert weighted[0][1] == 1.0
    comp = risk._dependency(entity(), weighted, {"ent_a": 60})
    assert comp["severity"] == "high"


def test_several_sole_sources_do_not_add_up_into_a_worse_finding():
    # Two irreplaceable suppliers at 90 leave you 90 exposed twice over, not 180 exposed.
    edges = [supply_edge("ent_a", "Alpha", sole=True), supply_edge("ent_b", "Bravo", sole=True)]
    comp = risk._dependency(entity(), risk.dependence_weights(edges), {"ent_a": 90, "ent_b": 90})
    assert "Exposure 90/100" in comp["detail"]
    assert "graded on the worst rather than added up" in comp["detail"]


def test_a_long_list_of_unremarkable_sole_sources_is_not_a_severe_finding():
    # The failure this replaced: eleven sole sources at single-digit risk summed to 54 and
    # reported a program as highly exposed, led by a supplier scoring 9. Structure is not
    # risk; how many there are belongs in the detail, not in the grade.
    edges = [supply_edge(f"ent_{i}", f"S{i}", sole=True) for i in range(11)]
    comp = risk._dependency(entity(), risk.dependence_weights(edges), {f"ent_{i}": 9 for i in range(11)})
    assert comp["severity"] == "clear"
    assert "Exposure 9/100" in comp["detail"] and "11 sole-source" in comp["detail"]


def test_one_bad_sole_source_among_benign_ones_still_leads():
    edges = [supply_edge(f"ent_{i}", f"S{i}", sole=True) for i in range(5)] + [supply_edge("ent_bad", "Trouble", sole=True)]
    scores = {f"ent_{i}": 5 for i in range(5)} | {"ent_bad": 70}
    comp = risk._dependency(entity(), risk.dependence_weights(edges), scores)
    assert comp["severity"] == "high"
    assert "Trouble" in comp["label"] and "Exposure 70/100" in comp["detail"]


def test_a_consumer_with_no_suppliers_is_not_graded_on_dependence():
    assert risk._dependency(entity(), [], {})["no_data"] is True


def test_suppliers_nobody_has_scored_abstain_and_are_named_as_missing():
    # They can only understate the exposure, so the reader has to be told it is a floor.
    edges = [supply_edge("ent_a", "Alpha", sole=True), supply_edge("ent_b", "Bravo")]
    comp = risk._dependency(entity(), risk.dependence_weights(edges), {"ent_a": 80})
    assert comp["severity"] == "high"
    assert "1 unscored and contributing nothing" in comp["detail"]


def test_a_consumer_whose_suppliers_are_all_unscored_is_not_graded_either():
    comp = risk._dependency(entity(), risk.dependence_weights([supply_edge("ent_a", "Alpha")]), {})
    assert comp["no_data"] is True and "none of them scored yet" in comp["detail"]


def test_the_exposure_carries_the_suppliers_and_edges_that_produced_it():
    edges = [supply_edge("ent_a", "Alpha", sole=True)]
    comp = risk._dependency(entity(), risk.dependence_weights(edges), {"ent_a": 80})
    assert comp["element_ids"] == ["ent_vendor", "ent_a", "rel_ent_a"]


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
        risk._dependency(entity(), [], {}),
    ])[0]
    hazardous = risk.composite([
        risk._designation(entity(), {"sanctions_screen": screen("sanctions_screen", "clear")}),
        risk._regional(entity(manufactures=["PH"])),
        risk._dependency(entity(), [], {}),
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
        risk._financial(row, {}, TODAY), risk._regional(row), risk._dependency(row, [], {}), risk._media({}),
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
    row = entity(registration_status="Active", incorporated=["US"], operates=["US-VT"], manufactures=["US-VT"])
    scored = risk._score([
        risk._designation(row, {"sanctions_screen": screen("sanctions_screen", "clear")}),
        risk._proximity_component(row, None), risk._foreign(row, []), risk._financial(row, {}, TODAY),
        risk._regional(row), risk._dependency(row, [(supply_edge('ent_a', 'Alpha'), 1.0)], {'ent_a': 0}),
        risk._media({"adverse_media_screen": screen("adverse_media_screen", "clear")}),
    ], row, "Entity")
    assert scored["confidence"] == 100 and "raise the confidence" not in scored["note"]


def test_every_dimension_the_scorer_emits_has_a_declared_weight():
    for name in ("designation", "proximity", "dependency", "foreign", "financial", "regional", "media"):
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
