"""The graph schema: labels, relationship types, constraints and the taxonomy.

This module is the allowlist the Cypher validator enforces (D3) and the source
of the schema description that goes into the model's cached system prompt (D8).
"""
from __future__ import annotations

from . import db

# --- Node labels -----------------------------------------------------------------
LABELS: dict[str, str] = {
    "Entity": "An organisation that supplies or consumes: company, agency, program. kind ∈ {organization, program, agency}.",
    "Person": "An executive, director or beneficial owner. Joined to entities by HELD_ROLE / BENEFICIAL_OWNER_OF.",
    "Category": "Goods or services taxonomy node. kind ∈ {goods, services}; hierarchical via SUBCATEGORY_OF.",
    "Location": "Country / region / city. kind ∈ {country, region, city}; code is ISO-3166 where applicable.",
    "Artifact": "Evidence: filing, award record, registry record, news article, web page. Never a raw blob.",
    "Claim": "Reified assertion (subject, predicate, object) with source, method, confidence, status ∈ {staged, committed, rejected}.",
}

# --- Relationship types ----------------------------------------------------------
RELS: dict[str, str] = {
    "SUPPLIES": "(supplier:Entity)-[:SUPPLIES {tier, sole_source, contract_ref, amount, psc, naics}]->(consumer:Entity)",
    "OWNS": "(parent:Entity)-[:OWNS {pct}]->(child:Entity) — direct ownership",
    "ULTIMATE_PARENT_OF": "(ultimate:Entity)-[:ULTIMATE_PARENT_OF]->(child:Entity)",
    "HELD_ROLE": "(p:Person)-[:HELD_ROLE {title, role_type ∈ {executive, board, both}, from, to, current}]->(e:Entity) — one edge per tenure",
    "BENEFICIAL_OWNER_OF": "(p:Person)-[:BENEFICIAL_OWNER_OF {pct}]->(e:Entity)",
    "PROVIDES": "(e:Entity)-[:PROVIDES]->(c:Category)",
    "SUBCATEGORY_OF": "(c:Category)-[:SUBCATEGORY_OF]->(parent:Category)",
    "INCORPORATED_IN": "(e:Entity)-[:INCORPORATED_IN]->(l:Location)",
    "OPERATES_IN": "(e:Entity)-[:OPERATES_IN]->(l:Location)",
    "MANUFACTURES_IN": "(e:Entity)-[:MANUFACTURES_IN]->(l:Location)",
    "PARENT_SEATED_IN": "(e:Entity)-[:PARENT_SEATED_IN]->(l:Location) — jurisdiction of the ultimate parent, denormalised for traversal",
    "EVIDENCES": "(a:Artifact)-[:EVIDENCES]->(c:Claim)",
    "ASSERTS": "(c:Claim)-[:ASSERTS]->(subject) — the claim's subject; predicate is a property on the Claim",
    "TARGETS": "(c:Claim)-[:TARGETS]->(object) — the claim's object node, when the object is a node",
    "ABOUT": "(a:Artifact)-[:ABOUT]->(e:Entity) — an artifact that mentions an entity without a specific claim",
}

# Provenance every node and edge written by the system carries (Entity metadata table).
PROVENANCE_FIELDS = ["source", "source_url", "retrieved_at", "method", "confidence", "claim_id"]

# Claim truth states used by deterministic consumers such as vendor-risk scoring.
# Only committed, non-simulated claims and artifacts are eligible as approved facts.
CLAIM_TRUTH_STATUSES = ("staged", "committed", "rejected")
APPROVED_TRUTH_STATUS = "committed"

# APOC procedures/functions the validator allows (read side).
APOC_ALLOWLIST = [
    "apoc.path.expand", "apoc.path.subgraphAll", "apoc.path.subgraphNodes", "apoc.path.spanningTree",
    "apoc.algo.dijkstra", "apoc.algo.allSimplePaths", "apoc.coll.", "apoc.text.", "apoc.map.",
    "apoc.convert.", "apoc.date.", "apoc.meta.stats", "apoc.node.degree", "apoc.nodes.connected",
]
# Write-side APOC that is permitted only through the permission gate.
APOC_WRITE_ALLOWLIST = ["apoc.create.", "apoc.merge.", "apoc.refactor."]

# --- Category taxonomy ----------------------------------------------------------
# kind: goods | services. Leaf categories map from PSC prefix / NAICS ranges in
# connectors/usaspending.py. Ids are stable so style_ops can reference them.
TAXONOMY: list[dict] = [
    {"id": "cat_goods", "name": "Goods", "kind": "goods", "parent": None},
    {"id": "cat_services", "name": "Services", "kind": "services", "parent": None},
    # goods
    {"id": "cat_aircraft_components", "name": "Aircraft components", "kind": "goods", "parent": "cat_goods"},
    {"id": "cat_engines", "name": "Engines & propulsion", "kind": "goods", "parent": "cat_aircraft_components"},
    {"id": "cat_avionics", "name": "Avionics & electronics", "kind": "goods", "parent": "cat_aircraft_components"},
    {"id": "cat_structures", "name": "Structures & airframe", "kind": "goods", "parent": "cat_aircraft_components"},
    {"id": "cat_metals", "name": "Metals", "kind": "goods", "parent": "cat_goods"},
    {"id": "cat_castings", "name": "Investment castings", "kind": "goods", "parent": "cat_metals"},
    {"id": "cat_hardware", "name": "Hardware & fasteners", "kind": "goods", "parent": "cat_goods"},
    {"id": "cat_it_hardware", "name": "IT hardware", "kind": "goods", "parent": "cat_goods"},
    {"id": "cat_weapons", "name": "Weapons & ordnance", "kind": "goods", "parent": "cat_goods"},
    {"id": "cat_vehicles", "name": "Vehicles & ground equipment", "kind": "goods", "parent": "cat_goods"},
    {"id": "cat_other_goods", "name": "Other goods", "kind": "goods", "parent": "cat_goods"},
    # services
    {"id": "cat_engineering", "name": "Engineering & technical services", "kind": "services", "parent": "cat_services"},
    {"id": "cat_maintenance", "name": "Maintenance, repair & overhaul", "kind": "services", "parent": "cat_services"},
    {"id": "cat_logistics", "name": "Logistics & supply support", "kind": "services", "parent": "cat_services"},
    {"id": "cat_it_services", "name": "IT & software services", "kind": "services", "parent": "cat_services"},
    {"id": "cat_professional", "name": "Professional & administrative services", "kind": "services", "parent": "cat_services"},
    {"id": "cat_legal", "name": "Legal services", "kind": "services", "parent": "cat_professional"},
    {"id": "cat_training", "name": "Training & education", "kind": "services", "parent": "cat_services"},
    {"id": "cat_rdte", "name": "Research & development", "kind": "services", "parent": "cat_services"},
    {"id": "cat_construction", "name": "Construction & facilities", "kind": "services", "parent": "cat_services"},
    {"id": "cat_other_services", "name": "Other services", "kind": "services", "parent": "cat_services"},
]

CONSTRAINTS = [
    "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (n:Entity) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT person_id IF NOT EXISTS FOR (n:Person) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT category_id IF NOT EXISTS FOR (n:Category) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT location_id IF NOT EXISTS FOR (n:Location) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT artifact_id IF NOT EXISTS FOR (n:Artifact) REQUIRE n.id IS UNIQUE",
    "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (n:Claim) REQUIRE n.id IS UNIQUE",
    "CREATE INDEX entity_uei IF NOT EXISTS FOR (n:Entity) ON (n.uei)",
    "CREATE INDEX entity_cage IF NOT EXISTS FOR (n:Entity) ON (n.cage)",
    "CREATE INDEX entity_lei IF NOT EXISTS FOR (n:Entity) ON (n.lei)",
    "CREATE INDEX entity_name IF NOT EXISTS FOR (n:Entity) ON (n.name_norm)",
    "CREATE INDEX person_name IF NOT EXISTS FOR (n:Person) ON (n.name_norm)",
    "CREATE INDEX claim_status IF NOT EXISTS FOR (n:Claim) ON (n.status)",
    "CREATE FULLTEXT INDEX entity_search IF NOT EXISTS FOR (n:Entity|Person) ON EACH [n.name, n.aliases_text]",
]


async def ensure_schema() -> None:
    for stmt in CONSTRAINTS:
        await db.write(stmt)
    for c in TAXONOMY:
        await db.write(
            "MERGE (c:Category {id:$id}) SET c.name=$name, c.kind=$kind, c.source='system'",
            {"id": c["id"], "name": c["name"], "kind": c["kind"]},
        )
    for c in TAXONOMY:
        if c["parent"]:
            await db.write(
                "MATCH (c:Category {id:$id}),(p:Category {id:$pid}) MERGE (c)-[:SUBCATEGORY_OF]->(p)",
                {"id": c["id"], "pid": c["parent"]},
            )


def schema_prompt() -> str:
    """Compact schema description for the system prompt. Kept constant so it caches."""
    lines = ["NODE LABELS:"]
    for k, v in LABELS.items():
        lines.append(f"  (:{k}) — {v}")
    lines.append("RELATIONSHIPS:")
    for k, v in RELS.items():
        lines.append(f"  {v}")
    lines.append("COMMON PROPERTIES: every node has id (string, e.g. 'ent_…', 'per_…', 'cat_…', 'loc_…', 'art_…', 'clm_…') and name. "
                 "Entity: uei, cage, lei, kind, aliases, registration_status, public (bool), ticker, summary, simulated (bool). "
                 "Location: code (ISO2 country / 'US-TX'), kind. Category: kind ∈ {goods, services}. "
                 "Edges carry an id property and provenance: " + ", ".join(PROVENANCE_FIELDS) + ".")
    lines.append("CATEGORY TAXONOMY (id → name, kind):")
    for c in TAXONOMY:
        lines.append(f"  {c['id']} → {c['name']} [{c['kind']}]" + (f" ⊂ {c['parent']}" if c["parent"] else ""))
    return "\n".join(lines)
