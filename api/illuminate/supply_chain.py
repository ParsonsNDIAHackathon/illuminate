"""Deterministic, bounded supply-chain findings for a program/root entity.

The database query deliberately returns a small snapshot.  Finding rules below
are pure functions so they can be tested against frozen rows without Neo4j.
"""
from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


def _eligible_rel(rel: str) -> str:
    return (
        f"(({rel}.claim_id IS NOT NULL AND EXISTS {{ "
        f"MATCH (truth:Claim {{id:{rel}.claim_id}}) WHERE truth.status='committed' "
        f"}}) OR ({rel}.claim_id IS NULL AND ({rel}.status IS NULL OR {rel}.status='committed') "
        f"AND {rel}.source IS NOT NULL AND {rel}.retrieved_at IS NOT NULL "
        f"AND {rel}.confidence IS NOT NULL))"
    )


def _evidence_simulated(rel: str) -> str:
    return (
        f"(coalesce({rel}.simulated,false) OR EXISTS {{ "
        f"MATCH (simclaim:Claim {{id:{rel}.claim_id}}) "
        f"WHERE coalesce(simclaim.simulated,false) OR EXISTS {{ "
        f"MATCH (simartifact:Artifact)-[simevidence:EVIDENCES]->(simclaim) "
        f"WHERE coalesce(simartifact.simulated,false) "
        f"OR coalesce(simevidence.simulated,false) }} }})"
    )


MAX_SUPPLY_DEPTH = 4
MAX_DEPENDENCIES = 500
MAX_CONTROL_DEPTH = 3
MAX_CONTROLS_PER_SUPPLIER = 25
MAX_ROLES_PER_SUPPLIER = 50
MAX_INTERLOCKS = 200
MAX_INTERLOCK_COMPARISONS = 10_000
MAX_CAPABILITIES_PER_DEPENDENCY = 25
MAX_MANUFACTURING_PER_DEPENDENCY = 25
MAX_COUNTRIES_PER_CONTROL = 10
MAX_CATEGORY_FINDINGS = 200
MAX_MANUFACTURING_FINDINGS = 200


SUPPLY_CHAIN_SNAPSHOT_CYPHER = f"""
MATCH (root:Entity {{id:$root_id}})
CALL {{
  WITH root
  CALL apoc.path.expandConfig(root, {{
    relationshipFilter:'<SUPPLIES',
    minLevel:1,
    maxLevel:{MAX_SUPPLY_DEPTH},
    bfs:true,
    uniqueness:'RELATIONSHIP_PATH',
    limit:{MAX_DEPENDENCIES + 1}
  }}) YIELD path
  WITH path, last(nodes(path)) AS supplier,
       reverse(relationships(path)) AS rels
  WITH supplier, path, rels, head(rels) AS edge
  ORDER BY length(path), supplier.id, [r IN rels | r.id], [node IN nodes(path) | node.id]
  // Materialize maps/scalars so later subqueries do not carry graph values
  // across an aggregation boundary in Neo4j 5.x.
  RETURN collect({{
    supplier_id:supplier.id, supplier_name:supplier.name, tier:length(path),
    supply_edge_id:edge.id, supply_edge_ids:[r IN rels | r.id],
    award:edge.contract_ref, award_count:coalesce(edge.award_count,1),
    award_context:CASE WHEN coalesce(edge.award_count,1)=1 THEN 'exact' ELSE 'representative' END,
    amount:edge.amount, sole_source:coalesce(edge.sole_source,false),
    capacity:edge.capacity, lead_time_days:edge.lead_time_days,
    component_criticality:edge.component_criticality, alternate_count:edge.alternate_count,
    confidence:coalesce(edge.confidence,supplier.confidence,0.5),
    freshness:coalesce(edge.freshness,supplier.freshness,'unknown'),
    source_count:coalesce(edge.source_count,1),
    truth_eligible:all(r IN rels WHERE {_eligible_rel("r")}),
    simulated:any(node IN nodes(path) WHERE coalesce(node.simulated,false))
              OR any(r IN rels WHERE {_evidence_simulated("r")}),
    graph_path:[node IN reverse(nodes(path)) | node{{.id,.name}}]
  }}) AS raw_candidate_paths
}}
WITH root, raw_candidate_paths[..{MAX_DEPENDENCIES}] AS scanned_supply_paths,
     size(raw_candidate_paths) > {MAX_DEPENDENCIES} AS supply_truncated
WITH root,[sp IN scanned_supply_paths WHERE sp.truth_eligible] AS supply_paths,supply_truncated
CALL {{
  WITH supply_paths
  UNWIND supply_paths AS sp
  MATCH (supplier:Entity {{id:sp.supplier_id}})
  CALL {{
    WITH supplier
    CALL apoc.path.expandConfig(supplier,{{
      relationshipFilter:'PROVIDES>',minLevel:1,maxLevel:1,bfs:true,
      uniqueness:'RELATIONSHIP_PATH',limit:{MAX_CAPABILITIES_PER_DEPENDENCY + 1}
    }}) YIELD path
    WITH last(nodes(path)) AS category,last(relationships(path)) AS provides
    WITH category,provides ORDER BY category.id,provides.id
    RETURN collect(category{{
         .id,.name,.kind,provides_edge_id:provides.id,
         confidence:provides.confidence,freshness:coalesce(provides.freshness,'unknown'),
         source_count:coalesce(provides.source_count,1),
         truth_eligible:{_eligible_rel("provides")},
         simulated:coalesce(category.simulated,false) OR {_evidence_simulated("provides")}
        }}) AS raw_categories
  }}
  CALL {{
    WITH supplier
    CALL apoc.path.expandConfig(supplier,{{
      relationshipFilter:'MANUFACTURES_IN>',minLevel:1,maxLevel:1,bfs:true,
      uniqueness:'RELATIONSHIP_PATH',limit:{MAX_MANUFACTURING_PER_DEPENDENCY + 1}
    }}) YIELD path
    WITH last(nodes(path)) AS place,last(relationships(path)) AS manufactures
    WITH place,manufactures ORDER BY place.id,manufactures.id
    RETURN collect(place{{
         .id,.name,.code,manufacturing_edge_id:manufactures.id,
         confidence:manufactures.confidence,freshness:coalesce(manufactures.freshness,'unknown'),
         source_count:coalesce(manufactures.source_count,1),
         truth_eligible:{_eligible_rel("manufactures")},
         simulated:coalesce(place.simulated,false) OR {_evidence_simulated("manufactures")}
        }}) AS raw_manufacturing
  }}
  WITH sp,
       [c IN raw_categories[..{MAX_CAPABILITIES_PER_DEPENDENCY}] WHERE c.id IS NOT NULL AND c.truth_eligible] AS categories,
       [place IN raw_manufacturing[..{MAX_MANUFACTURING_PER_DEPENDENCY}] WHERE place.id IS NOT NULL AND place.truth_eligible] AS manufacturing,
       size(raw_categories)>{MAX_CAPABILITIES_PER_DEPENDENCY} AS capabilities_truncated,
       size(raw_manufacturing)>{MAX_MANUFACTURING_PER_DEPENDENCY} AS manufacturing_truncated
  ORDER BY sp.supplier_id, sp.supply_edge_ids, sp.graph_path
  RETURN collect({{
    supplier_id:sp.supplier_id, supplier_name:sp.supplier_name, tier:sp.tier,
    supply_edge_id:sp.supply_edge_id, supply_edge_ids:sp.supply_edge_ids,
    categories:categories, manufacturing:manufacturing,
    capabilities_truncated:capabilities_truncated,manufacturing_truncated:manufacturing_truncated,
    award:sp.award, award_count:sp.award_count, award_context:sp.award_context,
    amount:sp.amount, sole_source:sp.sole_source,
    capacity:sp.capacity, lead_time_days:sp.lead_time_days,
    component_criticality:sp.component_criticality, alternate_count:sp.alternate_count,
    confidence:sp.confidence, freshness:sp.freshness, source_count:sp.source_count,
    simulated:sp.simulated,
    graph_path:sp.graph_path
  }}) AS dependencies
}}
CALL {{
  WITH supply_paths
  UNWIND supply_paths AS sp
  WITH sp ORDER BY sp.tier,sp.supplier_id,sp.supply_edge_ids,sp.graph_path
  WITH sp.supplier_id AS supplier_id, collect(sp)[0] AS sp
  MATCH (supplier:Entity {{id:sp.supplier_id}})
  CALL {{
    WITH supplier,sp
    CALL apoc.path.expandConfig(supplier,{{
      relationshipFilter:'<OWNS|<ULTIMATE_PARENT_OF',
      minLevel:1,maxLevel:{MAX_CONTROL_DEPTH},uniqueness:'NODE_PATH',
      limit:{MAX_CONTROLS_PER_SUPPLIER + 1}
    }}) YIELD path AS control
    WITH supplier,sp,control,last(nodes(control)) AS controller
    ORDER BY [r IN relationships(control) | r.id],[n IN nodes(control) | n.id]
    LIMIT {MAX_CONTROLS_PER_SUPPLIER + 1}
    WITH supplier,sp,collect({{
      controller_id:controller.id,controller_name:controller.name,
      control_edge_ids:[r IN relationships(control) | r.id],
      confidence:coalesce(last(relationships(control)).confidence,controller.confidence,0.5),
      freshness:coalesce(last(relationships(control)).freshness,controller.freshness,'unknown'),
      source_count:coalesce(last(relationships(control)).source_count,1),
      truth_eligible:all(r IN relationships(control) WHERE {_eligible_rel("r")}),
      simulated:sp.simulated
        OR any(n IN nodes(control) WHERE coalesce(n.simulated,false))
        OR any(r IN relationships(control) WHERE {_evidence_simulated("r")}),
      graph_path:reverse([n IN nodes(control) | n{{.id,.name}}]) + tail(sp.graph_path)
    }}) AS expanded
    CALL {{
      WITH supplier,sp,expanded
      UNWIND expanded[..{MAX_CONTROLS_PER_SUPPLIER}] AS control_data
      WITH supplier,sp,control_data WHERE control_data.truth_eligible
      MATCH (controller:Entity {{id:control_data.controller_id}})
       CALL {{
         WITH controller
         CALL apoc.path.expandConfig(controller,{{
           relationshipFilter:'INCORPORATED_IN>|PARENT_SEATED_IN>',minLevel:1,maxLevel:1,bfs:true,
           uniqueness:'RELATIONSHIP_PATH',limit:{MAX_COUNTRIES_PER_CONTROL + 1}
         }}) YIELD path
         WITH last(nodes(path)) AS country,last(relationships(path)) AS country_rel
         ORDER BY country.code,country.id,country_rel.id
         RETURN collect({{
           id:country.id,name:country.name,code:country.code,country_edge_id:country_rel.id,
           truth_eligible:{_eligible_rel("country_rel")},
           simulated:coalesce(country.simulated,false) OR {_evidence_simulated("country_rel")}
         }}) AS country_candidates
       }}
       WITH supplier,sp,controller,control_data,country_candidates,
            size(country_candidates)>{MAX_COUNTRIES_PER_CONTROL} AS country_truncated
       UNWIND country_candidates[..{MAX_COUNTRIES_PER_CONTROL}] AS country_data
       WITH supplier,sp,controller,control_data,country_data,country_truncated
       ORDER BY controller.id,country_data.code,control_data.control_edge_ids
       RETURN collect(CASE WHEN country_data.truth_eligible
         AND coalesce(country_data.code,'') <> '' AND NOT country_data.code STARTS WITH 'US'
         THEN {{
        supplier_id:supplier.id,supplier_name:supplier.name,
         controller_id:controller.id,controller_name:controller.name,country:country_data.code,tier:sp.tier,
        control_edge_ids:control_data.control_edge_ids,
        confidence:control_data.confidence,freshness:control_data.freshness,
        source_count:control_data.source_count,
        truth_eligible:true,
        simulated:control_data.simulated
           OR country_data.simulated,
        graph_path:control_data.graph_path
       }} END) AS foreign_found,
       coalesce(max(CASE WHEN country_truncated THEN 1 ELSE 0 END),0)=1 AS foreign_geo_truncated
    }}
    RETURN foreign_found AS found,
            size(expanded)>{MAX_CONTROLS_PER_SUPPLIER} OR foreign_geo_truncated AS traversal_truncated
  }}
  RETURN collect({{items:found[..{MAX_CONTROLS_PER_SUPPLIER}],
                   truncated:traversal_truncated OR size(found)>{MAX_CONTROLS_PER_SUPPLIER}}}) AS control_groups
}}
CALL {{
  WITH supply_paths
  UNWIND supply_paths AS sp
  WITH sp ORDER BY sp.tier,sp.supplier_id,sp.supply_edge_ids,sp.graph_path
  WITH sp.supplier_id AS supplier_id, collect(sp)[0] AS sp
  MATCH (supplier:Entity {{id:supplier_id}})
  CALL {{
    WITH supplier,sp
    CALL apoc.path.expandConfig(supplier,{{
      relationshipFilter:'<HELD_ROLE',minLevel:1,maxLevel:1,bfs:true,
      uniqueness:'RELATIONSHIP_PATH',limit:{MAX_ROLES_PER_SUPPLIER + 1}
    }}) YIELD path
    WITH last(nodes(path)) AS person,last(relationships(path)) AS role,supplier,sp
    WITH person,role,supplier,sp ORDER BY person.id,role.id
    RETURN collect({{
      person_id:person.id,person_name:person.name,
      entity_id:supplier.id,entity_name:supplier.name,tier:sp.tier,
      role_edge_id:role.id,role_from:toString(role.from),role_to:toString(role.to),
      role_current:coalesce(role.current,role.to IS NULL),
      confidence:coalesce(role.confidence,person.confidence,0.5),
      freshness:coalesce(role.freshness,person.freshness,'unknown'),
      source_count:coalesce(role.source_count,1),
      truth_eligible:{_eligible_rel("role")},
      simulated:sp.simulated OR coalesce(supplier.simulated,false)
        OR coalesce(person.simulated,false) OR {_evidence_simulated("role")}
    }}) AS found
  }}
  RETURN collect({{items:[role_data IN found[..{MAX_ROLES_PER_SUPPLIER}]
                         WHERE role_data.truth_eligible],
                   truncated:size(found)>{MAX_ROLES_PER_SUPPLIER}}}) AS role_groups
}}
WITH root,supply_paths,supply_truncated,dependencies,
     reduce(acc=[],g IN control_groups | acc+g.items) AS all_controls,
     any(g IN control_groups WHERE g.truncated) AS control_source_truncated,
     reduce(acc=[],g IN role_groups | acc+g.items) AS all_roles,
     any(g IN role_groups WHERE g.truncated) AS role_source_truncated
RETURN root{{.id,.name,.kind}} AS root,
       dependencies, all_controls[..{MAX_DEPENDENCIES}] AS controls, all_roles AS roles,
       {{
         supply_paths:{{returned:size(supply_paths),limit:{MAX_DEPENDENCIES},truncated:supply_truncated}},
          capabilities:{{returned:reduce(acc=0,d IN dependencies | acc+size(d.categories)),
                         limit:{MAX_CAPABILITIES_PER_DEPENDENCY},per_dependency_limit:{MAX_CAPABILITIES_PER_DEPENDENCY},
                         truncated:supply_truncated OR any(d IN dependencies WHERE d.capabilities_truncated),
                         selection_deterministic:NOT (supply_truncated OR any(d IN dependencies WHERE d.capabilities_truncated))}},
          manufacturing:{{returned:reduce(acc=0,d IN dependencies | acc+size(d.manufacturing)),
                          limit:{MAX_MANUFACTURING_PER_DEPENDENCY},per_dependency_limit:{MAX_MANUFACTURING_PER_DEPENDENCY},
                          truncated:supply_truncated OR any(d IN dependencies WHERE d.manufacturing_truncated),
                          selection_deterministic:NOT (supply_truncated OR any(d IN dependencies WHERE d.manufacturing_truncated))}},
         controls:{{returned:size(all_controls[..{MAX_DEPENDENCIES}]),limit:{MAX_DEPENDENCIES},
                    countries_per_control_limit:{MAX_COUNTRIES_PER_CONTROL},
                    truncated:supply_truncated OR control_source_truncated OR size(all_controls)>{MAX_DEPENDENCIES},
                    selection_deterministic:NOT (supply_truncated OR control_source_truncated OR size(all_controls)>{MAX_DEPENDENCIES})}},
          roles:{{returned:size(all_roles),limit:{MAX_DEPENDENCIES * MAX_ROLES_PER_SUPPLIER},
                  per_supplier_limit:{MAX_ROLES_PER_SUPPLIER},
                  truncated:supply_truncated OR role_source_truncated,
                  selection_deterministic:NOT (supply_truncated OR role_source_truncated)}}
       }} AS completeness
"""


class MissionContext(BaseModel):
    tier: int | None = None
    category: str | None = None
    dependency: str | None = None


class SupplyChainFinding(BaseModel):
    id: str
    finding_type: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    freshness: Literal["current", "aging", "stale", "unknown"]
    source_count: int = Field(ge=0)
    affected_program: str
    affected_award: str | None = None
    graph_path: list[dict[str, str | None]]
    narrative: str
    mission_context: MissionContext
    metrics: dict[str, Any] = Field(default_factory=dict)
    intelligence_gap: bool = False
    simulated: bool = False


class SupplyChainAnalysis(BaseModel):
    root_id: str
    root_name: str
    traversal: dict[str, int]
    completeness: dict[str, dict[str, int | bool]]
    includes_simulated: bool = False
    findings: list[SupplyChainFinding]


def _path(value: Any, root: dict[str, Any], dependency: dict[str, Any] | None = None) -> list[dict[str, str | None]]:
    nodes: list[dict[str, str | None]] = []
    for item in value or []:
        if isinstance(item, dict):
            nodes.append({"node_id": item.get("id"), "node_name": item.get("name")})
        else:
            nodes.append({"node_id": None, "node_name": str(item)})
    if not nodes and dependency:
        nodes.append({"node_id": dependency.get("supplier_id"), "node_name": dependency.get("supplier_name")})
        nodes.append({"node_id": root.get("id"), "node_name": root.get("name")})
    return nodes or [{"node_id": root.get("id"), "node_name": root.get("name")}]


def _categories(dependency: dict[str, Any]) -> list[str]:
    values = dependency.get("categories")
    if values is None:
        values = [dependency.get("category")]
    names = {
        str(value.get("name") or value.get("id"))
        if isinstance(value, dict) else str(value)
        for value in values or []
        if value
    }
    return sorted(names) or ["Unknown category"]


def _category(dependency: dict[str, Any]) -> str:
    return ", ".join(_categories(dependency))


def _observed_categories(dependency: dict[str, Any]) -> list[str]:
    """Only eligible Category/PROVIDES maps constitute observed capability."""
    return sorted({
        str(value.get("name") or value.get("id"))
        for value in dependency.get("categories", []) or []
        if isinstance(value, dict) and _truth_eligible(value)
        and (value.get("name") or value.get("id"))
    })


def _evidence(row: dict[str, Any]) -> tuple[float, str, int]:
    confidence = max(0.0, min(1.0, float(row.get("confidence") or 0.0)))
    freshness = str(row.get("freshness") or "unknown").lower()
    if freshness not in {"current", "aging", "stale", "unknown"}:
        freshness = "unknown"
    return confidence, freshness, max(0, int(row.get("source_count") or 0))


def _truth_eligible(row: dict[str, Any]) -> bool:
    """Defense in depth; legacy explicit fixtures without truth metadata remain valid."""
    if "truth_eligible" in row:
        return row.get("truth_eligible") is True
    if row.get("claim_id"):
        return row.get("claim_status") == "committed"
    if row.get("status") not in (None, "committed"):
        return False
    if row.get("evidence_contract"):
        return bool(row.get("source") and row.get("retrieved_at") and row.get("confidence") is not None)
    return True


def _row_simulated(row: dict[str, Any]) -> bool:
    return bool(
        row.get("simulated") or row.get("claim_simulated")
        or row.get("artifact_simulated")
    )


def _path_key(row: dict[str, Any]) -> tuple:
    return tuple((str(node.get("id")), str(node.get("name"))) for node in row.get("graph_path", []) if isinstance(node, dict))


def _dependency_key(row: dict[str, Any]) -> tuple:
    return (
        int(row.get("tier") or 0),
        str(row.get("supplier_id") or ""),
        str(row.get("supply_edge_id") or ""),
        tuple(str(edge_id) for edge_id in row.get("supply_edge_ids", []) or []),
        str(row.get("award") or ""),
        tuple(_categories(row)),
        _path_key(row),
        json.dumps(row, sort_keys=True, default=str, separators=(",", ":")),
    )


def _relationship_id(row: dict[str, Any]) -> str:
    """Identity of the supplied dependency, stable across diamond-shaped paths."""
    if row.get("supply_edge_id"):
        return str(row["supply_edge_id"])
    edge_ids = row.get("supply_edge_ids") or []
    if edge_ids:
        return str(edge_ids[0])
    return f"{row.get('supplier_id')}|{row.get('award') or ''}"


def _aggregate_evidence(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate distinct supported facts, independent of input ordering."""
    ordered = sorted(rows, key=_dependency_key)
    if not ordered:
        return {}
    unique = {_relationship_id(row): row for row in reversed(ordered)}
    evidence = [(_evidence(row), row) for row in unique.values()]
    total_sources = sum(item[0][2] for item in evidence)
    confidence = (
        sum(values[0] * max(values[2], 1) for values, _ in evidence)
        / sum(max(values[2], 1) for values, _ in evidence)
    )
    freshness_rank = {"unknown": 0, "stale": 1, "aging": 2, "current": 3}
    freshness = min((values[1] for values, _ in evidence), key=lambda value: freshness_rank[value])
    out = dict(ordered[0])
    out.update(
        confidence=round(confidence, 6), freshness=freshness, source_count=total_sources,
        simulated=any(_row_simulated(row) for row in unique.values()),
    )
    return out


def _canonical_relationships(paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in paths:
        groups[_relationship_id(row)].append(row)
    output = []
    for relationship_id, rows in sorted(groups.items()):
        ordered = sorted(rows, key=_dependency_key)
        merged = dict(ordered[0])
        merged["supply_edge_id"] = relationship_id
        merged["tier"] = min(int(row.get("tier") or 0) for row in rows)
        merged["capabilities_truncated"] = any(
            bool(row.get("capabilities_truncated")) for row in rows
        )
        merged["manufacturing_truncated"] = any(
            bool(row.get("manufacturing_truncated")) for row in rows
        )
        capabilities: dict[tuple[str, str, str], dict[str, Any]] = {}
        for row in rows:
            for capability in row.get("categories", []):
                if not isinstance(capability, dict) or not _truth_eligible(capability):
                    continue
                key = (
                    str(capability.get("provides_edge_id") or ""),
                    str(capability.get("id") or ""),
                    str(capability.get("name") or ""),
                )
                candidate = dict(capability)
                current = capabilities.get(key)
                if current is None:
                    capabilities[key] = candidate
                else:
                    ordered_pair = sorted(
                        (current, candidate),
                        key=lambda item: json.dumps(item, sort_keys=True, default=str, separators=(",", ":")),
                    )
                    merged_capability = dict(ordered_pair[0])
                    current_evidence, candidate_evidence = _evidence(current), _evidence(candidate)
                    rank = {"unknown": 0, "stale": 1, "aging": 2, "current": 3}
                    merged_capability.update(
                        confidence=min(current_evidence[0], candidate_evidence[0]),
                        freshness=min(
                            (current_evidence[1], candidate_evidence[1]),
                            key=lambda value: rank[value],
                        ),
                        source_count=max(current_evidence[2], candidate_evidence[2]),
                        simulated=_row_simulated(current) or _row_simulated(candidate),
                    )
                    capabilities[key] = merged_capability
        merged["categories"] = [capabilities[key] for key in sorted(capabilities)]
        if len(merged["categories"]) > MAX_CAPABILITIES_PER_DEPENDENCY:
            merged["capabilities_truncated"] = True
            merged["categories"] = merged["categories"][:MAX_CAPABILITIES_PER_DEPENDENCY]
        places = {
            (
                str(place.get("manufacturing_edge_id") or ""),
                str(place.get("id") or ""), str(place.get("code") or ""), str(place.get("name") or ""),
            ): place
            for row in rows for place in row.get("manufacturing", [])
            if isinstance(place, dict) and _truth_eligible(place)
        }
        merged["manufacturing"] = [places[key] for key in sorted(places)]
        if len(merged["manufacturing"]) > MAX_MANUFACTURING_PER_DEPENDENCY:
            merged["manufacturing_truncated"] = True
            merged["manufacturing"] = merged["manufacturing"][:MAX_MANUFACTURING_PER_DEPENDENCY]
        evidence = _aggregate_evidence(rows)
        merged.update(
            confidence=evidence.get("confidence", 0),
            freshness=evidence.get("freshness", "unknown"),
            source_count=evidence.get("source_count", 0),
            simulated=any(_row_simulated(row) for row in rows),
        )
        output.append(merged)
    return output


def _aggregate_record_groups(
    rows: list[dict[str, Any]],
    group_key,
    evidence_key,
) -> list[dict[str, Any]]:
    groups: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[group_key(row)].append(row)
    output = []
    rank = {"unknown": 0, "stale": 1, "aging": 2, "current": 3}
    for key in sorted(groups):
        ordered = sorted(
            groups[key],
            key=lambda row: json.dumps(row, sort_keys=True, default=str, separators=(",", ":")),
        )
        unique = {}
        for row in ordered:
            unique.setdefault(evidence_key(row), row)
        evidence = [_evidence(row) for row in unique.values()]
        denominator = sum(max(values[2], 1) for values in evidence)
        merged = dict(ordered[0])
        merged.update(
            confidence=round(
                sum(values[0] * max(values[2], 1) for values in evidence) / denominator,
                6,
            ),
            freshness=min((values[1] for values in evidence), key=lambda value: rank[value]),
            source_count=sum(values[2] for values in evidence),
            simulated=any(_row_simulated(row) for row in unique.values()),
        )
        output.append(merged)
    return output


def _roles_overlap(a: dict[str, Any], b: dict[str, Any]) -> str | None:
    if a.get("role_current") and b.get("role_current"):
        return "current"
    if not a.get("role_from") or not b.get("role_from"):
        return None
    if (not a.get("role_current") and not a.get("role_to")) or (
        not b.get("role_current") and not b.get("role_to")
    ):
        return None
    a_start = str(a["role_from"])
    b_start = str(b["role_from"])
    a_end = "9999-12-31" if a.get("role_current") else str(a["role_to"])
    b_end = "9999-12-31" if b.get("role_current") else str(b["role_to"])
    return "overlapping" if a_start <= b_end and b_start <= a_end else None


def _build_interlocks(roles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Construct bounded interlocks from already bounded per-supplier role rows."""
    ordered = sorted(
        (
            row for row in roles
            if row.get("person_id") and row.get("entity_id") and row.get("role_edge_id")
            and _truth_eligible(row)
        ),
        key=lambda row: (
            str(row.get("person_id")), str(row.get("entity_id")), str(row.get("role_edge_id")),
            json.dumps(row, sort_keys=True, default=str, separators=(",", ":")),
        ),
    )
    candidates: list[dict[str, Any]] = []
    comparisons = 0
    by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in ordered:
        by_person[str(row["person_id"])].append(row)
    for person_id in sorted(by_person):
        person_roles = by_person[person_id]
        for index, a in enumerate(person_roles):
            for b in person_roles[index + 1:]:
                if comparisons >= MAX_INTERLOCK_COMPARISONS:
                    return candidates, True
                comparisons += 1
                if str(a["entity_id"]) >= str(b["entity_id"]):
                    continue
                overlap = _roles_overlap(a, b)
                if not overlap:
                    continue
                evidence = _aggregate_record_groups(
                    [a, b], lambda _: ("roles",), lambda row: str(row["role_edge_id"])
                )[0]
                candidates.append({
                    "person_id": person_id,
                    "person_name": a.get("person_name") or b.get("person_name"),
                    "entity_a_id": a["entity_id"], "entity_a_name": a.get("entity_name"),
                    "entity_b_id": b["entity_id"], "entity_b_name": b.get("entity_name"),
                    "role_a_edge_id": a["role_edge_id"], "role_b_edge_id": b["role_edge_id"],
                    "overlap_kind": overlap,
                    "confidence": evidence["confidence"], "freshness": evidence["freshness"],
                    "source_count": evidence["source_count"],
                    "simulated": _row_simulated(a) or _row_simulated(b),
                    "graph_path": [
                        {"id": a["entity_id"], "name": a.get("entity_name")},
                        {"id": person_id, "name": a.get("person_name") or b.get("person_name")},
                        {"id": b["entity_id"], "name": b.get("entity_name")},
                    ],
                })
                if len(candidates) > MAX_INTERLOCKS:
                    return candidates[:MAX_INTERLOCKS], True
    return candidates, False


def _exact_award(row: dict[str, Any]) -> str | None:
    if row.get("award") and int(row.get("award_count") or 1) == 1 and row.get("award_context", "exact") == "exact":
        return str(row["award"])
    return None


def _combine_context_evidence(
    supply: dict[str, Any], context: dict[str, Any], edge_key: str, edge_label: str,
) -> dict[str, Any]:
    supply_confidence, supply_freshness, supply_sources = _evidence(supply)
    context_confidence, context_freshness, context_sources = _evidence(context)
    rank = {"unknown": 0, "stale": 1, "aging": 2, "current": 3}
    combined = dict(supply)
    combined.update(
        confidence=min(supply_confidence, context_confidence),
        freshness=min((supply_freshness, context_freshness), key=lambda value: rank[value]),
        source_count=supply_sources + context_sources,
        simulated=_row_simulated(supply) or _row_simulated(context),
    )
    graph_path = list(supply.get("graph_path") or [])
    if context.get(edge_key):
        graph_path.append({"id": str(context[edge_key]), "name": edge_label})
    graph_path.append({"id": context.get("id"), "name": context.get("name") or context.get("code")})
    combined["graph_path"] = graph_path
    return combined


def _with_capability_context(dependency: dict[str, Any]) -> dict[str, Any]:
    """Include every displayed supplier-capability fact in finding provenance."""
    contexts = sorted(
        (
            item for item in dependency.get("categories", [])
            if isinstance(item, dict) and _truth_eligible(item)
        ),
        key=lambda item: (
            str(item.get("provides_edge_id") or ""),
            str(item.get("id") or ""),
            str(item.get("name") or ""),
        ),
    )
    contextual = dict(dependency)
    contextual["simulated"] = _row_simulated(dependency) or any(
        _row_simulated(item) for item in contexts
    )
    evidenced = [
        item for item in contexts
        if item.get("provides_edge_id")
        or item.get("confidence") is not None
        or item.get("source_count") is not None
        or item.get("freshness") is not None
    ]
    if not evidenced:
        return contextual
    confidence, freshness, source_count = _evidence(dependency)
    rank = {"unknown": 0, "stale": 1, "aging": 2, "current": 3}
    contextual.update(
        confidence=min([confidence, *(_evidence(item)[0] for item in evidenced)]),
        freshness=min(
            [freshness, *(_evidence(item)[1] for item in evidenced)],
            key=lambda value: rank[value],
        ),
        source_count=source_count + sum(_evidence(item)[2] for item in evidenced),
    )
    first = evidenced[0]
    graph_path = list(dependency.get("graph_path") or [])
    if first.get("provides_edge_id"):
        graph_path.append({"id": str(first["provides_edge_id"]), "name": "PROVIDES"})
    graph_path.append({"id": first.get("id"), "name": first.get("name")})
    contextual["graph_path"] = graph_path
    return contextual


def _finding(
    root: dict[str, Any], finding_type: str, severity: str, narrative: str,
    row: dict[str, Any], *, tier: int | None = None, category: str | None = None,
    dependency: str | None = None, award: str | None = None,
    metrics: dict[str, Any] | None = None, gap: bool = False,
    fact_identity: str,
) -> SupplyChainFinding:
    confidence, freshness, source_count = _evidence(row)
    signature = "|".join((str(root.get("id")), finding_type, fact_identity))
    return SupplyChainFinding(
        id="scf_" + sha256(signature.encode()).hexdigest()[:16],
        finding_type=finding_type,
        severity=severity,
        confidence=confidence,
        freshness=freshness,
        source_count=source_count,
        affected_program=root.get("id") or root.get("name") or "unknown",
        affected_award=award,
        graph_path=_path(row.get("graph_path"), root, row),
        narrative=narrative,
        mission_context=MissionContext(tier=tier, category=category, dependency=dependency),
        metrics=metrics or {},
        intelligence_gap=gap,
        simulated=_row_simulated(row),
    )


def analyze_supply_chain(snapshot: dict[str, Any]) -> SupplyChainAnalysis | None:
    """Apply stable rules to one database snapshot. Input ordering cannot affect output."""
    root = snapshot.get("root")
    if not isinstance(root, dict) or not root.get("id"):
        return None
    supply_paths = sorted(
        (
            d for d in snapshot.get("dependencies", [])
            if isinstance(d, dict) and d.get("supplier_id") and _truth_eligible(d)
        ),
        key=_dependency_key,
    )[:MAX_DEPENDENCIES]
    dependencies = _canonical_relationships(supply_paths)
    raw_controls = sorted(
        (
            c for c in snapshot.get("controls", [])
            if isinstance(c, dict) and _truth_eligible(c)
        ),
        key=lambda c: (
            str(c.get("supplier_id")), str(c.get("controller_id")), str(c.get("country")),
            _path_key(c), str(c.get("confidence")), str(c.get("freshness")), int(c.get("source_count") or 0),
            json.dumps(c, sort_keys=True, default=str, separators=(",", ":")),
        ),
    )[:MAX_DEPENDENCIES]
    controls = _aggregate_record_groups(
        raw_controls,
        lambda row: (
            str(row.get("supplier_id")), str(row.get("controller_id")), str(row.get("country")),
        ),
        lambda row: tuple(str(value) for value in row.get("control_edge_ids", []) or [])
        or (str(row.get("controller_id")), str(row.get("supplier_id"))),
    )
    built_interlocks, interlock_sentinel_truncated = _build_interlocks(
        [row for row in snapshot.get("roles", []) if isinstance(row, dict)]
    )
    raw_interlocks = sorted(
        (
            i for i in [*built_interlocks, *snapshot.get("interlocks", [])]
            if isinstance(i, dict)
            and i.get("role_a_edge_id") and i.get("role_b_edge_id")
            and i.get("overlap_kind") in {"current", "overlapping"}
            and _truth_eligible(i)
        ),
        key=lambda i: (
            str(i.get("person_id")), str(i.get("entity_a_id")), str(i.get("entity_b_id")),
            str(i.get("role_a_edge_id")), str(i.get("role_b_edge_id")), _path_key(i),
            json.dumps(i, sort_keys=True, default=str, separators=(",", ":")),
        ),
    )[:MAX_INTERLOCKS]
    interlocks = _aggregate_record_groups(
        raw_interlocks,
        lambda row: (
            str(row.get("person_id")), str(row.get("entity_a_id")),
            str(row.get("entity_b_id")), str(row.get("overlap_kind")),
        ),
        lambda row: (str(row.get("role_a_edge_id")), str(row.get("role_b_edge_id"))),
    )
    findings: list[SupplyChainFinding] = []
    program_name = root.get("name") or root["id"]

    if supply_paths:
        max_depth = max(int(d.get("tier") or 0) for d in supply_paths)
        # The evidence path must itself demonstrate the stated maximum depth.
        deepest = [row for row in supply_paths if int(row.get("tier") or 0) == max_depth]
        evidence = sorted(deepest, key=_dependency_key)[0]
        findings.append(_finding(
            root, "supplier_depth", "high" if max_depth >= 4 else "medium" if max_depth >= 3 else "low",
            f"{program_name} has observed supplier dependencies through tier {max_depth}.",
            evidence, tier=max_depth, dependency=program_name,
            metrics={"maximum_tier": max_depth},
            fact_identity=f"depth:{max_depth}:{'|'.join(map(str, evidence.get('supply_edge_ids', [])))}",
        ))
        unique_suppliers = {str(d["supplier_id"]) for d in dependencies}
        dependency_evidence = _aggregate_evidence(dependencies)
        findings.append(_finding(
            root, "dependency_count", "medium" if len(unique_suppliers) >= 10 else "low",
            f"{program_name} depends on {len(unique_suppliers)} observed supplier(s) across {len(dependencies)} supply relationship(s).",
            dependency_evidence, dependency=program_name,
            metrics={"supplier_count": len(unique_suppliers), "relationship_count": len(dependencies)},
            fact_identity="dependencies:" + ",".join(sorted(_relationship_id(row) for row in dependencies)),
        ))

    by_category: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for dep in dependencies:
        for category in _observed_categories(dep):
            by_category[category].append(dep)

    for category, rows in sorted(by_category.items()):
        contributor_map: dict[tuple[str, str, str], tuple[dict[str, Any], dict[str, Any]]] = {}
        for row in rows:
            contexts = [
                item for item in row.get("categories", [])
                if isinstance(item, dict)
                and str(item.get("name") or item.get("id")) == category
                and _truth_eligible(item)
            ] or [{"name": category}]
            for context in contexts:
                key = (
                    str(context.get("provides_edge_id") or f"legacy:{_relationship_id(row)}"),
                    str(context.get("id") or context.get("name") or ""),
                    str(row.get("supplier_id") or ""),
                )
                contributor_map.setdefault(key, (row, context))
        contributors = [contributor_map[key] for key in sorted(contributor_map)]
        counts: dict[str, int] = defaultdict(int)
        for row, _ in contributors:
            counts[str(row["supplier_id"])] += 1
        top_id, top_count = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0]
        share = top_count / len(contributors)
        if share >= 0.5:
            top_support = sorted(
                (
                    _combine_context_evidence(row, context, "provides_edge_id", "PROVIDES")
                    for row, context in contributors if str(row["supplier_id"]) == top_id
                ),
                key=_dependency_key,
            )[0]
            evidence_rows: list[dict[str, Any]] = []
            for row in rows:
                supply_evidence = dict(row)
                supply_evidence["_context_evidence_id"] = f"supply:{_relationship_id(row)}"
                evidence_rows.append(supply_evidence)
            for _, context in contributors:
                capability_evidence = dict(context)
                capability_evidence["_context_evidence_id"] = (
                    f"provides:{context.get('provides_edge_id') or context.get('id') or context.get('name')}"
                )
                evidence_rows.append(capability_evidence)
            aggregate = _aggregate_record_groups(
                evidence_rows, lambda _: ("category",),
                lambda item: str(item["_context_evidence_id"]),
            )[0]
            top = dict(top_support)
            top.update(
                confidence=aggregate["confidence"], freshness=aggregate["freshness"],
                source_count=aggregate["source_count"], simulated=aggregate["simulated"],
            )
            provides_ids = sorted({
                str(context["provides_edge_id"])
                for _, context in contributors if context.get("provides_edge_id")
            })
            findings.append(_finding(
                root, "category_concentration", "high" if share == 1 else "medium",
                f"{top.get('supplier_name') or top_id} represents {share:.0%} of supplier capability "
                f"records for {category} associated with program dependencies; dependency-specific category is unverified.",
                top, tier=int(top.get("tier") or 0), category=category,
                dependency=top.get("supplier_name") or top_id,
                metrics={"capability_share": round(share, 4), "capability_records": len(contributors),
                         "category_scope": "supplier_capability",
                         "dependency_specific_category_verified": False},
                fact_identity=f"category:{category}:"
                              + ",".join(sorted(_relationship_id(row) for row in rows))
                              + ":provides:" + ",".join(provides_ids),
            ))

    # Tier-1 SUPPLIES.amount is a supplier aggregate in the seed, not an award
    # amount. Keep this explicitly at supplier-exposure level.
    tier_one = [row for row in dependencies if int(row.get("tier") or 0) == 1 and row.get("amount") is not None]
    supplier_amounts: dict[str, float] = defaultdict(float)
    for row in tier_one:
        supplier_amounts[str(row["supplier_id"])] += float(row.get("amount") or 0)
    total_tier_one = sum(supplier_amounts.values())
    if total_tier_one > 0 and supplier_amounts:
        top_id, top_amount = sorted(supplier_amounts.items(), key=lambda item: (-item[1], item[0]))[0]
        share = top_amount / total_tier_one
        if share >= 0.5:
            top_rows = [row for row in tier_one if str(row["supplier_id"]) == top_id]
            row = _aggregate_evidence(top_rows)
            row["simulated"] = any(bool(item.get("simulated")) for item in tier_one)
            findings.append(_finding(
                root, "tier_1_supplier_exposure_concentration", "high" if share >= 0.75 else "medium",
                f"{row.get('supplier_name') or top_id} represents {share:.0%} of observed tier-1 supplier exposure.",
                row, tier=1, category=None, dependency=row.get("supplier_name") or top_id,
                metrics={"supplier_exposure_share": round(share, 4), "supplier_aggregate_amount": top_amount},
                fact_identity="tier1-exposure:" + ",".join(sorted(_relationship_id(item) for item in tier_one)),
            ))

    for dep in dependencies:
        supplier = dep.get("supplier_name") or dep["supplier_id"]
        tier = int(dep.get("tier") or 0)
        category = _category(dep)
        contextual_dep = _with_capability_context(dep)
        award = _exact_award(dep)
        edge_identity = _relationship_id(dep)
        if not _observed_categories(dep):
            findings.append(_finding(
                root, "intelligence_gap_category", "medium",
                f"Supplier capability category evidence is unknown for the tier {tier} dependency on {supplier}.",
                dep, tier=tier, category=None, dependency=supplier, award=award,
                metrics={"unknown_field": "category", "intelligence_gap": True}, gap=True,
                fact_identity=f"supply:{edge_identity}:unknown:category",
            ))
        if dep.get("sole_source") is True:
            findings.append(_finding(
                root, "sole_source", "critical" if tier <= 1 else "high",
                f"{supplier} is recorded as the sole source for a tier {tier} dependency. Supplier capability "
                f"context includes {category}; dependency-specific category is unverified.",
                contextual_dep, tier=tier, category=category, dependency=supplier, award=award,
                metrics={"sole_source": True, "category_scope": "supplier_capability",
                         "dependency_specific_category_verified": False},
                fact_identity=f"supply:{edge_identity}:sole-source",
            ))
        if dep.get("alternate_count") == 0:
            findings.append(_finding(
                root, "alternate_source_gap", "critical" if dep.get("sole_source") else "high",
                f"No alternate source is recorded for the tier {tier} dependency on {supplier}. Supplier "
                f"capability context is {category}; dependency-specific category is unverified.",
                contextual_dep, tier=tier, category=category, dependency=supplier, award=award,
                metrics={"alternate_count": 0, "category_scope": "supplier_capability",
                         "dependency_specific_category_verified": False},
                fact_identity=f"supply:{edge_identity}:alternate-gap",
            ))
        unknowns = (
            ("capacity", "supplier capacity"),
            ("lead_time_days", "lead time"),
            ("component_criticality", "component criticality"),
            ("alternate_count", "alternate sources"),
        )
        for field, label in unknowns:
            if dep.get(field) is None:
                findings.append(_finding(
                    root, f"intelligence_gap_{field}", "medium",
                    f"{label.capitalize()} is unknown for the tier {tier} dependency on {supplier}. Supplier "
                    f"capability context is {category}; dependency-specific category is unverified.",
                    contextual_dep, tier=tier, category=category, dependency=supplier, award=award,
                    metrics={"unknown_field": field, "category_scope": "supplier_capability",
                             "dependency_specific_category_verified": False}, gap=True,
                    fact_identity=f"supply:{edge_identity}:unknown:{field}",
                ))

        manufacturing = sorted(
            (place for place in dep.get("manufacturing", []) if isinstance(place, dict)),
            key=lambda place: (
                str(place.get("manufacturing_edge_id") or ""),
                str(place.get("code")), str(place.get("id")), str(place.get("name")),
            ),
        )
        for place in manufacturing:
            code = str(place.get("code") or "")
            if code and not code.startswith("US"):
                manufacturing_edge_id = str(place.get("manufacturing_edge_id") or "unknown")
                location_id = str(place.get("id") or code)
                combined = _combine_context_evidence(
                    contextual_dep, place, "manufacturing_edge_id", "MANUFACTURES_IN"
                )
                findings.append(_finding(
                    root, "manufacturing_geography", "high",
                    f"{supplier} has supplier-level manufacturing exposure in {place.get('name') or code} "
                    f"({code}) relevant to a tier {tier} program dependency; dependency-specific production "
                    f"location is unverified.",
                    combined, tier=tier, category=category, dependency=supplier, award=None,
                    metrics={
                        "geography_scope": "supplier",
                        "dependency_specific_location_verified": False,
                        "country_code": code,
                        "manufacturing_edge_id": manufacturing_edge_id,
                        "category_scope": "supplier_capability",
                        "dependency_specific_category_verified": False,
                    },
                    fact_identity=f"supply:{edge_identity}:manufacturing:{manufacturing_edge_id}:"
                                  f"{location_id}:{code}",
                ))

    for control in controls:
        supplier = control.get("supplier_name") or control.get("supplier_id") or "Supplier"
        controller = control.get("controller_name") or control.get("controller_id") or "an unnamed controller"
        tier = int(control.get("tier") or 0)
        country = control.get("country") or "an unknown foreign jurisdiction"
        findings.append(_finding(
            root, "foreign_control", "critical" if tier <= 1 else "high",
            f"{supplier} has an ownership or control path to {controller} in {country}.",
            control, tier=tier, dependency=supplier,
            metrics={"controller": controller, "country_code": country},
            fact_identity="control:"
                          + ",".join(map(str, control.get("control_edge_ids", [])))
                          + f":{control.get('controller_id')}:{country}",
        ))

    for interlock in interlocks:
        person = interlock.get("person_name") or interlock.get("person_id") or "A leader"
        a = interlock.get("entity_a_name") or interlock.get("entity_a_id") or "one supplier"
        b = interlock.get("entity_b_name") or interlock.get("entity_b_id") or "another supplier"
        overlap_kind = interlock["overlap_kind"]
        timing = "currently" if overlap_kind == "current" else "during overlapping tenures"
        findings.append(_finding(
            root, "leadership_interlock", "medium",
            f"{person} holds leadership roles at both {a} and {b} {timing}, linking two program dependencies.",
            interlock, dependency=f"{a}; {b}",
            metrics={"person": person, "linked_entities": [a, b], "tenure_relation": overlap_kind},
            fact_identity=f"roles:{interlock.get('person_id')}:{interlock.get('role_a_edge_id')}:"
                          f"{interlock.get('role_b_edge_id')}",
        ))

    # Parallel graph paths can describe the same supported fact. Stable ids make
    # that fact idempotent while retaining distinct awards and dependencies.
    findings = list({finding.id: finding for finding in findings}.values())
    findings.sort(key=lambda finding: (finding.finding_type, finding.id))
    category_finding_truncated = sum(
        finding.finding_type == "category_concentration" for finding in findings
    ) > MAX_CATEGORY_FINDINGS
    manufacturing_finding_truncated = sum(
        finding.finding_type == "manufacturing_geography" for finding in findings
    ) > MAX_MANUFACTURING_FINDINGS
    type_limits = {
        "category_concentration": MAX_CATEGORY_FINDINGS,
        "manufacturing_geography": MAX_MANUFACTURING_FINDINGS,
    }
    emitted_by_type: dict[str, int] = defaultdict(int)
    bounded_findings = []
    for finding in findings:
        limit = type_limits.get(finding.finding_type)
        if limit is None or emitted_by_type[finding.finding_type] < limit:
            bounded_findings.append(finding)
            emitted_by_type[finding.finding_type] += 1
    findings = bounded_findings
    raw_completeness = snapshot.get("completeness") or {}
    defaults = {
        "supply_paths": {"returned": len(supply_paths), "limit": MAX_DEPENDENCIES, "truncated": False},
        "capabilities": {
            "returned": sum(len(dep.get("categories", [])) for dep in dependencies),
            "limit": MAX_CAPABILITIES_PER_DEPENDENCY,
            "per_dependency_limit": MAX_CAPABILITIES_PER_DEPENDENCY,
            "truncated": False,
            "selection_deterministic": True,
        },
        "manufacturing": {
            "returned": sum(len(dep.get("manufacturing", [])) for dep in dependencies),
            "limit": MAX_MANUFACTURING_PER_DEPENDENCY,
            "per_dependency_limit": MAX_MANUFACTURING_PER_DEPENDENCY,
            "truncated": False,
            "selection_deterministic": True,
        },
        "controls": {
            "returned": len(raw_controls), "limit": MAX_DEPENDENCIES,
            "countries_per_control_limit": MAX_COUNTRIES_PER_CONTROL,
            "truncated": False, "selection_deterministic": True,
        },
        "roles": {
            "returned": len(snapshot.get("roles", [])),
            "limit": MAX_DEPENDENCIES * MAX_ROLES_PER_SUPPLIER,
            "per_supplier_limit": MAX_ROLES_PER_SUPPLIER,
            "truncated": False,
            "selection_deterministic": True,
        },
        "interlocks": {"returned": len(raw_interlocks), "limit": MAX_INTERLOCKS,
                       "truncated": interlock_sentinel_truncated},
    }
    completeness = {}
    for key, default in defaults.items():
        supplied = raw_completeness.get(key) if isinstance(raw_completeness, dict) else None
        value = {**default, **(supplied if isinstance(supplied, dict) else {})}
        if key != "supply_paths":
            supply = raw_completeness.get("supply_paths") if isinstance(raw_completeness, dict) else None
            if isinstance(supply, dict) and supply.get("truncated"):
                value["truncated"] = True
        if key == "interlocks":
            roles_meta = raw_completeness.get("roles") if isinstance(raw_completeness, dict) else None
            if isinstance(roles_meta, dict) and roles_meta.get("truncated"):
                value["truncated"] = True
        if key == "capabilities" and category_finding_truncated:
            value["truncated"] = True
        if key == "capabilities" and any(
            bool(dep.get("capabilities_truncated")) for dep in dependencies
        ):
            value["truncated"] = True
        if key == "manufacturing" and manufacturing_finding_truncated:
            value["truncated"] = True
        if key == "manufacturing" and any(
            bool(dep.get("manufacturing_truncated")) for dep in dependencies
        ):
            value["truncated"] = True
        if key in {"capabilities", "manufacturing", "controls", "roles"}:
            value["selection_deterministic"] = not bool(value["truncated"])
        value["complete"] = not bool(value["truncated"])
        completeness[key] = value
    return SupplyChainAnalysis(
        root_id=root["id"],
        root_name=program_name,
        traversal={
            "max_supply_depth": MAX_SUPPLY_DEPTH,
            "max_control_depth": MAX_CONTROL_DEPTH,
            "max_dependencies": MAX_DEPENDENCIES,
            "max_controls_per_supplier": MAX_CONTROLS_PER_SUPPLIER,
            "max_countries_per_control": MAX_COUNTRIES_PER_CONTROL,
            "max_roles_per_supplier": MAX_ROLES_PER_SUPPLIER,
            "max_interlocks": MAX_INTERLOCKS,
            "max_interlock_comparisons": MAX_INTERLOCK_COMPARISONS,
        },
        completeness=completeness,
        includes_simulated=any(finding.simulated for finding in findings),
        findings=findings,
    )


async def get_supply_chain_analysis(root_id: str) -> SupplyChainAnalysis | None:
    from . import db

    rows = await db.read(SUPPLY_CHAIN_SNAPSHOT_CYPHER, {"root_id": root_id})
    return analyze_supply_chain(rows[0]) if rows else None