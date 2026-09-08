"""Supply-chain rules use frozen rows; no test in this module connects to Neo4j."""
from __future__ import annotations

from copy import deepcopy

import pytest

from illuminate import db
from illuminate.supply_chain import (
    MAX_CONTROL_DEPTH,
    MAX_CAPABILITIES_PER_DEPENDENCY,
    MAX_CONTROLS_PER_SUPPLIER,
    MAX_DEPENDENCIES,
    MAX_INTERLOCK_COMPARISONS,
    MAX_INTERLOCKS,
    MAX_ROLES_PER_SUPPLIER,
    MAX_SUPPLY_DEPTH,
    MAX_MANUFACTURING_PER_DEPENDENCY,
    SUPPLY_CHAIN_SNAPSHOT_CYPHER,
    _canonical_relationships,
    analyze_supply_chain,
    get_supply_chain_analysis,
)


FROZEN_SNAPSHOT = {
    "root": {"id": "prog_f35", "name": "F-35 Sustainment", "kind": "program"},
    "dependencies": (
        {
            "supplier_id": "ent_prime",
            "supplier_name": "Prime Air",
            "tier": 1,
            "supply_edge_id": "sup_prime_program",
            "supply_edge_ids": ("sup_prime_program",),
            "categories": (
                {"id": "cat_avionics", "name": "Avionics & electronics"},
                {"id": "cat_maintenance", "name": "Maintenance, repair & overhaul"},
            ),
            "award": "AWD-001",
            "award_count": 3,
            "award_context": "representative",
            "amount": 80,
            "sole_source": True,
            "capacity": None,
            "lead_time_days": None,
            "component_criticality": None,
            "alternate_count": 0,
            "manufacturing": ({
                "id": "loc_gb", "name": "United Kingdom", "code": "GB",
                "manufacturing_edge_id": "mfg_prime_gb",
                "confidence": 0.6, "freshness": "stale", "source_count": 2,
                "simulated": False,
            },),
            "confidence": 0.92,
            "freshness": "current",
            "source_count": 3,
            "graph_path": (
                {"id": "ent_prime", "name": "Prime Air"},
                {"id": "prog_f35", "name": "F-35 Sustainment"},
            ),
        },
        {
            "supplier_id": "ent_chip",
            "supplier_name": "Chip Foundry",
            "tier": 3,
            "supply_edge_id": "sup_chip_sub",
            "supply_edge_ids": ("sup_chip_sub", "sup_sub_prime", "sup_prime_program"),
            "categories": ({"id": "cat_avionics", "name": "Avionics & electronics"},),
            "award": "AWD-002",
            "award_count": 1,
            "award_context": "exact",
            "amount": 20,
            "sole_source": False,
            "capacity": 1000,
            "lead_time_days": 120,
            "component_criticality": "mission_critical",
            "alternate_count": None,
            "manufacturing": (),
            "confidence": 0.71,
            "freshness": "aging",
            "source_count": 2,
            "graph_path": (
                {"id": "ent_chip", "name": "Chip Foundry"},
                {"id": "ent_sub", "name": "Subsystem Co"},
                {"id": "ent_prime", "name": "Prime Air"},
                {"id": "prog_f35", "name": "F-35 Sustainment"},
            ),
        },
    ),
    "controls": (
        {
            "supplier_id": "ent_chip",
            "supplier_name": "Chip Foundry",
            "controller_id": "ent_foreign",
            "controller_name": "Foreign Holdings",
            "country": "CN",
            "tier": 3,
            "confidence": 0.8,
            "freshness": "current",
            "source_count": 2,
            "graph_path": (
                {"id": "ent_foreign", "name": "Foreign Holdings"},
                {"id": "ent_chip", "name": "Chip Foundry"},
                {"id": "prog_f35", "name": "F-35 Sustainment"},
            ),
        },
    ),
    "interlocks": (
        {
            "person_id": "per_shared",
            "person_name": "Alex Director",
            "entity_a_id": "ent_chip",
            "entity_a_name": "Chip Foundry",
            "entity_b_id": "ent_prime",
            "entity_b_name": "Prime Air",
            "role_a_edge_id": "role_chip",
            "role_b_edge_id": "role_prime",
            "overlap_kind": "current",
            "confidence": 0.75,
            "freshness": "aging",
            "source_count": 2,
            "graph_path": (
                {"id": "ent_chip", "name": "Chip Foundry"},
                {"id": "per_shared", "name": "Alex Director"},
                {"id": "ent_prime", "name": "Prime Air"},
            ),
        },
    ),
}


def test_representative_snapshot_exposes_all_supply_chain_rules_and_contract_fields():
    result = analyze_supply_chain(FROZEN_SNAPSHOT)
    assert result is not None
    types = {finding.finding_type for finding in result.findings}
    assert {
        "supplier_depth",
        "dependency_count",
        "category_concentration",
        "tier_1_supplier_exposure_concentration",
        "sole_source",
        "foreign_control",
        "leadership_interlock",
        "manufacturing_geography",
        "alternate_source_gap",
        "intelligence_gap_capacity",
        "intelligence_gap_lead_time_days",
        "intelligence_gap_component_criticality",
        "intelligence_gap_alternate_count",
    } <= types

    for finding in result.findings:
        assert finding.severity in {"info", "low", "medium", "high", "critical"}
        assert 0 <= finding.confidence <= 1
        assert finding.freshness in {"current", "aging", "stale", "unknown"}
        assert finding.source_count >= 0
        assert finding.affected_program == "prog_f35"
        assert finding.graph_path
        assert len(finding.narrative) < 220
        # Pydantic preserves the explicit mission keys even when a dimension is unknown.
        assert set(finding.mission_context.model_dump()) == {"tier", "category", "dependency"}

    sole_source = next(f for f in result.findings if f.finding_type == "sole_source")
    assert sole_source.affected_award is None
    assert sole_source.mission_context.tier == 1
    assert sole_source.mission_context.category == "Avionics & electronics, Maintenance, repair & overhaul"
    assert sole_source.severity == "critical"


def test_analysis_is_deterministic_and_declares_hard_traversal_bounds():
    forward = analyze_supply_chain(deepcopy(FROZEN_SNAPSHOT))
    reversed_rows = deepcopy(FROZEN_SNAPSHOT)
    reversed_rows["dependencies"] = tuple(reversed(reversed_rows["dependencies"]))
    assert analyze_supply_chain(reversed_rows).model_dump() == forward.model_dump()
    assert forward.traversal["max_supply_depth"] == MAX_SUPPLY_DEPTH
    assert forward.traversal["max_control_depth"] == MAX_CONTROL_DEPTH
    assert forward.traversal["max_dependencies"] == MAX_DEPENDENCIES
    assert forward.traversal["max_controls_per_supplier"] == MAX_CONTROLS_PER_SUPPLIER
    assert forward.traversal["max_roles_per_supplier"] == MAX_ROLES_PER_SUPPLIER
    assert forward.traversal["max_interlock_comparisons"] == MAX_INTERLOCK_COMPARISONS
    assert forward.completeness["roles"]["per_supplier_limit"] == MAX_ROLES_PER_SUPPLIER
    assert forward.traversal["max_interlocks"] == MAX_INTERLOCKS
    assert forward.completeness["supply_paths"]["complete"] is True


@pytest.mark.asyncio
async def test_get_analysis_uses_mocked_read_and_handles_missing_root(monkeypatch):
    calls = []

    async def read(cypher, params):
        calls.append((cypher, params))
        return [FROZEN_SNAPSHOT]

    monkeypatch.setattr(db, "read", read)
    result = await get_supply_chain_analysis("prog_f35")
    assert result.root_id == "prog_f35"
    assert calls[0][1] == {"root_id": "prog_f35"}
    assert f"maxLevel:{MAX_SUPPLY_DEPTH}" in calls[0][0]
    assert f"maxLevel:{MAX_CONTROL_DEPTH}" in calls[0][0]
    assert "apoc.path.expandConfig" in calls[0][0]
    assert f"limit:{MAX_DEPENDENCIES + 1}" in calls[0][0]
    assert f"limit:{MAX_CONTROLS_PER_SUPPLIER + 1}" in calls[0][0]
    assert f"limit:{MAX_ROLES_PER_SUPPLIER + 1}" in calls[0][0]
    assert "relationshipFilter:'<HELD_ROLE'" in calls[0][0]
    assert "award_count:coalesce(edge.award_count,1)" in calls[0][0]
    assert "truth.status='committed'" in calls[0][0]
    assert "r.source IS NOT NULL" in calls[0][0]
    assert "[simevidence:EVIDENCES]" in calls[0][0]
    # Regression for Neo4j 5.26: aggregate maps contain only scalar/map values;
    # later subqueries rematch nodes by id rather than dereferencing a node/path.
    assert "MATCH (supplier:Entity {id:sp.supplier_id})" in calls[0][0]
    assert "supplier:supplier,path:path,rels:rels" not in calls[0][0]
    assert "sp.supplier AS" not in calls[0][0]
    assert "sp.rels" not in calls[0][0]
    assert "sp.path" not in calls[0][0]
    assert "WITH DISTINCT supplier,sp,controller,control,country" not in calls[0][0]

    async def no_rows(cypher, params):
        return []

    monkeypatch.setattr(db, "read", no_rows)
    assert await get_supply_chain_analysis("missing") is None


def test_interlocks_require_two_roles_and_current_or_overlapping_tenures():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    snapshot["interlocks"] = (
        {
            "person_id": "missing_role",
            "person_name": "Missing Role",
            "entity_a_id": "ent_chip",
            "entity_b_id": "ent_prime",
            "role_a_edge_id": "role_a",
            "overlap_kind": "current",
        },
        {
            "person_id": "old_roles",
            "person_name": "Old Roles",
            "entity_a_id": "ent_chip",
            "entity_b_id": "ent_prime",
            "role_a_edge_id": "role_a",
            "role_b_edge_id": "role_b",
            "overlap_kind": "non_overlapping",
        },
    )
    result = analyze_supply_chain(snapshot)
    assert not [f for f in result.findings if f.finding_type == "leadership_interlock"]


def test_complete_tie_ordering_is_permutation_stable():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    tied_a = deepcopy(snapshot["dependencies"][1])
    tied_b = deepcopy(tied_a)
    tied_a.update(confidence=0.4, source_count=1)
    tied_b.update(confidence=0.9, source_count=4)
    snapshot["dependencies"] = (tied_a, tied_b, snapshot["dependencies"][0])
    forward = analyze_supply_chain(snapshot).model_dump()
    snapshot["dependencies"] = tuple(reversed(snapshot["dependencies"]))
    assert analyze_supply_chain(snapshot).model_dump() == forward


def test_diamond_paths_do_not_double_count_relationship_metrics_or_evidence():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    duplicate_path = deepcopy(snapshot["dependencies"][1])
    duplicate_path.update(
        tier=4,
        graph_path=(
            {"id": "ent_chip", "name": "Chip Foundry"},
            {"id": "ent_other", "name": "Other Subsystem"},
            {"id": "ent_sub", "name": "Subsystem Co"},
            {"id": "ent_prime", "name": "Prime Air"},
            {"id": "prog_f35", "name": "F-35 Sustainment"},
        ),
    )
    snapshot["dependencies"] = snapshot["dependencies"] + (duplicate_path,)
    result = analyze_supply_chain(snapshot)
    count = next(f for f in result.findings if f.finding_type == "dependency_count")
    assert count.metrics == {"supplier_count": 2, "relationship_count": 2}
    assert count.source_count == 5
    avionics = next(
        f for f in result.findings
        if f.finding_type == "category_concentration"
        and f.mission_context.category == "Avionics & electronics"
    )
    assert avionics.metrics["capability_records"] == 2


def test_depth_finding_uses_evidence_from_a_deepest_path():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    deep = deepcopy(snapshot["dependencies"][1])
    deep.update(
        tier=4,
        supply_edge_id="sup_deep",
        supply_edge_ids=("sup_deep", "sup_3", "sup_2", "sup_1"),
        supplier_id="ent_deep",
        supplier_name="Deep Supplier",
        graph_path=(
            {"id": "ent_deep", "name": "Deep Supplier"},
            {"id": "ent_3", "name": "Tier Three"},
            {"id": "ent_2", "name": "Tier Two"},
            {"id": "ent_prime", "name": "Prime Air"},
            {"id": "prog_f35", "name": "F-35 Sustainment"},
        ),
        confidence=0.1,
        source_count=1,
    )
    snapshot["dependencies"] = snapshot["dependencies"] + (deep,)
    depth = next(
        f for f in analyze_supply_chain(snapshot).findings
        if f.finding_type == "supplier_depth"
    )
    assert depth.metrics["maximum_tier"] == 4
    assert depth.graph_path[0]["node_id"] == "ent_deep"
    assert len(depth.graph_path) == 5


def test_snapshot_truncation_is_exposed_as_incomplete():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    snapshot["completeness"] = {
        "supply_paths": {"returned": 500, "limit": 500, "truncated": True},
        "controls": {"returned": 1, "limit": 500, "truncated": False},
        "interlocks": {"returned": 1, "limit": 200, "truncated": False},
    }
    completeness = analyze_supply_chain(snapshot).completeness
    assert completeness["supply_paths"] == {
        "returned": 500, "limit": 500, "truncated": True, "complete": False,
    }
    assert completeness["controls"]["complete"] is False
    assert completeness["interlocks"]["complete"] is False


def test_tier_one_exposure_and_representative_award_semantics():
    result = analyze_supply_chain(deepcopy(FROZEN_SNAPSHOT))
    types = {finding.finding_type for finding in result.findings}
    assert "award_concentration" not in types
    exposure = next(f for f in result.findings if f.finding_type == "tier_1_supplier_exposure_concentration")
    assert exposure.affected_award is None
    assert "supplier exposure" in exposure.narrative
    assert "award exposure" not in exposure.narrative
    sole = next(f for f in result.findings if f.finding_type == "sole_source")
    assert sole.affected_award is None
    assert "AWD-001" not in sole.narrative
    exact = next(f for f in result.findings if f.finding_type == "intelligence_gap_alternate_count")
    assert exact.affected_award == "AWD-002"


def test_finding_ids_use_root_and_stable_fact_identity():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    first = deepcopy(snapshot["dependencies"][0])
    second = deepcopy(first)
    second.update(
        supply_edge_id="sup_prime_other",
        supply_edge_ids=("sup_prime_other", "sup_other_program"),
        graph_path=(
            {"id": "ent_prime", "name": "Prime Air"},
            {"id": "ent_other", "name": "Other Intermediate"},
            {"id": "prog_f35", "name": "F-35 Sustainment"},
        ),
    )
    diamond = deepcopy(first)
    diamond["graph_path"] = (
        {"id": "ent_prime", "name": "Prime Air"},
        {"id": "ent_diamond", "name": "Diamond Intermediate"},
        {"id": "prog_f35", "name": "F-35 Sustainment"},
    )
    snapshot["dependencies"] = (first, second, diamond)
    sole_ids = {
        f.id for f in analyze_supply_chain(snapshot).findings
        if f.finding_type == "sole_source"
    }
    assert len(sole_ids) == 2
    other_root = deepcopy(snapshot)
    other_root["root"] = {"id": "prog_other", "name": "Other Program", "kind": "program"}
    other_ids = {
        f.id for f in analyze_supply_chain(other_root).findings
        if f.finding_type == "sole_source"
    }
    assert sole_ids.isdisjoint(other_ids)


def test_simulated_evidence_propagates_to_findings_and_aggregates():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    simulated = deepcopy(snapshot["dependencies"][0])
    simulated["simulated"] = True
    snapshot["dependencies"] = (simulated, snapshot["dependencies"][1])
    snapshot["interlocks"] = ()
    snapshot["roles"] = (
        {
            "person_id": "per_sim", "person_name": "Sim Person",
            "entity_id": "ent_chip", "entity_name": "Chip Foundry",
            "role_edge_id": "role_sim_a", "role_current": True,
            "confidence": .8, "freshness": "current", "source_count": 1, "simulated": True,
        },
        {
            "person_id": "per_sim", "person_name": "Sim Person",
            "entity_id": "ent_prime", "entity_name": "Prime Air",
            "role_edge_id": "role_sim_b", "role_current": True,
            "confidence": .8, "freshness": "current", "source_count": 1, "simulated": False,
        },
    )
    result = analyze_supply_chain(snapshot)
    assert result.includes_simulated is True
    assert next(f for f in result.findings if f.finding_type == "dependency_count").simulated is True
    assert next(f for f in result.findings if f.finding_type == "leadership_interlock").simulated is True
    assert all(isinstance(f.simulated, bool) for f in result.findings)


def test_downstream_sentinels_propagate_completeness():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    snapshot["completeness"] = {
        "supply_paths": {"returned": 2, "limit": 500, "truncated": False},
        "controls": {"returned": 25, "limit": 500, "truncated": True},
        "roles": {"returned": 50, "limit": 50, "truncated": True},
    }
    completeness = analyze_supply_chain(snapshot).completeness
    assert completeness["supply_paths"]["complete"] is True
    assert completeness["controls"]["complete"] is False
    assert completeness["roles"]["complete"] is False
    assert completeness["interlocks"]["complete"] is False


def test_truth_ineligible_rows_never_support_findings():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    rejected = deepcopy(snapshot["dependencies"][0])
    rejected.update(claim_id="clm_changed", claim_status="rejected")
    snapshot["dependencies"] = (rejected,)
    snapshot["controls"] = ({**snapshot["controls"][0], "truth_eligible": False},)
    snapshot["interlocks"] = ({**snapshot["interlocks"][0], "truth_eligible": False},)
    result = analyze_supply_chain(snapshot)
    assert not result.findings


def test_claim_and_artifact_simulation_propagates_defensively():
    for marker in ("claim_simulated", "artifact_simulated"):
        snapshot = deepcopy(FROZEN_SNAPSHOT)
        row = deepcopy(snapshot["dependencies"][0])
        row[marker] = True
        snapshot["dependencies"] = (row, snapshot["dependencies"][1])
        result = analyze_supply_chain(snapshot)
        sole = next(f for f in result.findings if f.finding_type == "sole_source")
        assert sole.simulated is True
        assert result.includes_simulated is True


def test_two_non_current_undated_roles_do_not_prove_an_interlock():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    snapshot["interlocks"] = ()
    snapshot["roles"] = (
        {
            "person_id": "per_unknown", "person_name": "Unknown Tenure",
            "entity_id": "ent_chip", "entity_name": "Chip Foundry",
            "role_edge_id": "role_unknown_a", "role_current": False,
        },
        {
            "person_id": "per_unknown", "person_name": "Unknown Tenure",
            "entity_id": "ent_prime", "entity_name": "Prime Air",
            "role_edge_id": "role_unknown_b", "role_current": False,
        },
    )
    result = analyze_supply_chain(snapshot)
    assert not [f for f in result.findings if f.finding_type == "leadership_interlock"]


def test_supplier_manufacturing_exposure_preserves_edge_evidence_without_award_attribution():
    finding = next(
        f for f in analyze_supply_chain(deepcopy(FROZEN_SNAPSHOT)).findings
        if f.finding_type == "manufacturing_geography"
    )
    assert finding.affected_award is None
    assert "supplier-level manufacturing exposure" in finding.narrative
    assert "dependency-specific production location is unverified" in finding.narrative
    assert finding.metrics == {
        "geography_scope": "supplier",
        "dependency_specific_location_verified": False,
        "country_code": "GB",
        "manufacturing_edge_id": "mfg_prime_gb",
        "category_scope": "supplier_capability",
        "dependency_specific_category_verified": False,
    }
    assert finding.confidence == 0.6
    assert finding.freshness == "stale"
    assert finding.source_count == 5
    assert [step["node_id"] for step in finding.graph_path[-2:]] == [
        "mfg_prime_gb", "loc_gb",
    ]


def test_category_findings_are_supplier_capability_context_not_dependency_attribution():
    finding = next(
        f for f in analyze_supply_chain(deepcopy(FROZEN_SNAPSHOT)).findings
        if f.finding_type == "category_concentration"
    )
    assert finding.metrics["category_scope"] == "supplier_capability"
    assert finding.metrics["dependency_specific_category_verified"] is False
    assert "dependency-specific category is unverified" in finding.narrative


def test_nested_provides_lineage_survives_canonicalization_and_denominator_aggregation():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    prime = deepcopy(snapshot["dependencies"][0])
    chip = deepcopy(snapshot["dependencies"][1])
    prime["simulated"] = False
    prime["categories"] = (
        {
            "id": "cat_avionics", "name": "Avionics & electronics", "kind": "goods",
            "provides_edge_id": "provides_prime_avionics",
            "confidence": 0.55, "freshness": "stale", "source_count": 2,
            "simulated": True,
        },
    )
    chip["categories"] = (
        {
            "id": "cat_avionics", "name": "Avionics & electronics", "kind": "goods",
            "provides_edge_id": "provides_chip_avionics",
            "confidence": 0.65, "freshness": "aging", "source_count": 1,
            "simulated": False,
        },
    )
    snapshot["dependencies"] = (prime, chip)
    canonical = _canonical_relationships(list(snapshot["dependencies"]))
    prime_capability = next(
        row["categories"][0] for row in canonical if row["supplier_id"] == "ent_prime"
    )
    assert prime_capability == {
        "id": "cat_avionics", "name": "Avionics & electronics", "kind": "goods",
        "provides_edge_id": "provides_prime_avionics",
        "confidence": 0.55, "freshness": "stale", "source_count": 2,
        "simulated": True,
    }
    result = analyze_supply_chain(snapshot)
    finding = next(
        f for f in result.findings
        if f.finding_type == "category_concentration"
        and f.mission_context.category == "Avionics & electronics"
    )
    # Chip Foundry is the deterministic tied top supplier, while simulated
    # prime capability evidence still participates in denominator lineage.
    assert finding.mission_context.dependency == "Chip Foundry"
    assert finding.simulated is True
    assert result.includes_simulated is True
    assert finding.freshness == "stale"
    assert finding.source_count == 8  # both supply edges + both PROVIDES edges
    assert finding.graph_path[-2]["node_id"] == "provides_chip_avionics"
    assert finding.graph_path[-1]["node_id"] == "cat_avionics"
    changed = deepcopy(snapshot)
    changed["dependencies"][0]["categories"][0]["provides_edge_id"] = "provides_prime_changed"
    changed_finding = next(
        f for f in analyze_supply_chain(changed).findings
        if f.finding_type == "category_concentration"
        and f.mission_context.category == "Avionics & electronics"
    )
    assert changed_finding.id != finding.id


def test_nested_manufacturing_simulation_sets_finding_and_analysis_flags():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    prime = deepcopy(snapshot["dependencies"][0])
    prime["simulated"] = False
    place = deepcopy(prime["manufacturing"][0])
    place["simulated"] = True
    prime["manufacturing"] = (place,)
    snapshot["dependencies"] = (prime, snapshot["dependencies"][1])
    result = analyze_supply_chain(snapshot)
    finding = next(f for f in result.findings if f.finding_type == "manufacturing_geography")
    assert finding.simulated is True
    assert result.includes_simulated is True


def test_simulated_capability_marks_every_finding_that_displays_its_context():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    prime = deepcopy(snapshot["dependencies"][0])
    prime["simulated"] = False
    prime["categories"] = ({
        "id": "cat_simulated",
        "name": "Simulated capability",
        "provides_edge_id": "provides_simulated",
        "confidence": 0.8,
        "freshness": "current",
        "source_count": 1,
        "simulated": True,
    },)
    snapshot["dependencies"] = (prime, snapshot["dependencies"][1])
    result = analyze_supply_chain(snapshot)
    contextual_types = {
        "sole_source",
        "alternate_source_gap",
        "intelligence_gap_capacity",
        "intelligence_gap_lead_time_days",
        "intelligence_gap_component_criticality",
        "manufacturing_geography",
    }
    contextual_findings = [
        finding for finding in result.findings
        if finding.finding_type in contextual_types
        and finding.mission_context.dependency == "Prime Air"
    ]
    assert contextual_findings
    assert all(finding.simulated for finding in contextual_findings)
    assert result.includes_simulated is True


def test_absent_or_rejected_categories_emit_gap_not_synthetic_concentration():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    prime = deepcopy(snapshot["dependencies"][0])
    chip = deepcopy(snapshot["dependencies"][1])
    prime["categories"] = ()
    chip["categories"] = ({"id": "cat_rejected", "name": "Rejected", "truth_eligible": False},)
    snapshot["dependencies"] = (prime, chip)
    result = analyze_supply_chain(snapshot)
    gaps = [f for f in result.findings if f.finding_type == "intelligence_gap_category"]
    assert {f.mission_context.dependency for f in gaps} == {"Prime Air", "Chip Foundry"}
    assert all(f.intelligence_gap for f in gaps)
    assert not any(
        f.finding_type == "category_concentration"
        and f.mission_context.category in {"Unknown category", "Rejected"}
        for f in result.findings
    )


def test_context_fanout_is_capped_and_marks_context_completeness_incomplete():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    dep = deepcopy(snapshot["dependencies"][0])
    dep["categories"] = tuple(
        {"id": f"cat_{index}", "name": f"Capability {index}",
         "provides_edge_id": f"provides_{index}"}
        for index in range(1100)
    )
    dep["manufacturing"] = tuple(
        {"id": f"loc_{index}", "name": f"Location {index}", "code": "GB",
         "manufacturing_edge_id": f"manufactures_{index}"}
        for index in range(1100)
    )
    snapshot["dependencies"] = (dep,)
    result = analyze_supply_chain(snapshot)
    assert len([f for f in result.findings if f.finding_type == "category_concentration"]) <= MAX_CAPABILITIES_PER_DEPENDENCY
    assert len([f for f in result.findings if f.finding_type == "manufacturing_geography"]) <= MAX_MANUFACTURING_PER_DEPENDENCY
    assert result.completeness["capabilities"]["complete"] is False
    assert result.completeness["manufacturing"]["complete"] is False
    assert result.completeness["capabilities"]["selection_deterministic"] is False
    assert result.completeness["manufacturing"]["selection_deterministic"] is False


def test_context_query_uses_independent_bounded_subqueries_without_cartesian_optional_matches():
    for relationship_filter, limit in (
        ("PROVIDES>", 26), ("MANUFACTURES_IN>", 26),
        ("<HELD_ROLE", 51), ("INCORPORATED_IN>|PARENT_SEATED_IN>", 11),
    ):
        assert f"relationshipFilter:'{relationship_filter}'" in SUPPLY_CHAIN_SNAPSHOT_CYPHER
        assert f"limit:{limit}" in SUPPLY_CHAIN_SNAPSHOT_CYPHER
    assert "minLevel:1,maxLevel:1,bfs:true" in SUPPLY_CHAIN_SNAPSHOT_CYPHER
    assert "uniqueness:'RELATIONSHIP_PATH'" in SUPPLY_CHAIN_SNAPSHOT_CYPHER
    assert "[:PROVIDES]" not in SUPPLY_CHAIN_SNAPSHOT_CYPHER
    assert "[:MANUFACTURES_IN]" not in SUPPLY_CHAIN_SNAPSHOT_CYPHER
    assert "[role:HELD_ROLE]" not in SUPPLY_CHAIN_SNAPSHOT_CYPHER
    assert "[country_rel:INCORPORATED_IN|PARENT_SEATED_IN]" not in SUPPLY_CHAIN_SNAPSHOT_CYPHER
    assert SUPPLY_CHAIN_SNAPSHOT_CYPHER.count("selection_deterministic:") == 4


def test_concentration_lineage_includes_simulated_denominator_rows():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    simulated = deepcopy(snapshot["dependencies"][0])
    simulated.update(
        supplier_id="ent_simulated",
        supplier_name="Scenario Supplier",
        supply_edge_id="sup_simulated_program",
        supply_edge_ids=("sup_simulated_program",),
        amount=20,
        sole_source=False,
        simulated=True,
    )
    snapshot["dependencies"] = snapshot["dependencies"] + (simulated,)
    findings = analyze_supply_chain(snapshot).findings
    category = next(
        finding for finding in findings
        if finding.finding_type == "category_concentration"
        and finding.mission_context.category == "Maintenance, repair & overhaul"
    )
    exposure = next(
        finding for finding in findings
        if finding.finding_type == "tier_1_supplier_exposure_concentration"
    )
    assert category.simulated is True
    assert exposure.simulated is True


def test_nonmatching_interlock_work_stops_at_comparison_budget():
    snapshot = deepcopy(FROZEN_SNAPSHOT)
    snapshot["interlocks"] = ()
    role_count = 150
    snapshot["roles"] = tuple(
        {
            "person_id": "per_many_roles",
            "person_name": "Historical Leader",
            "entity_id": f"ent_{index:03}",
            "entity_name": f"Supplier {index:03}",
            "role_edge_id": f"role_{index:03}",
            "role_from": f"{1800 + index:04}-01-01",
            "role_to": f"{1800 + index:04}-12-31",
            "role_current": False,
            "confidence": 0.8,
            "freshness": "aging",
            "source_count": 1,
            "simulated": False,
        }
        for index in range(role_count)
    )
    result = analyze_supply_chain(snapshot)
    assert not [
        finding for finding in result.findings
        if finding.finding_type == "leadership_interlock"
    ]
    assert result.completeness["interlocks"]["complete"] is False