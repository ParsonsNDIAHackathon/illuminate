from illuminate.cypher.templates import TEMPLATES, match_intent
from illuminate.cypher.validator import validate


def test_all_templates_validate_as_reads():
    sample = {"entity_id": "ent_x", "root_id": "ent_root", "country": "CN", "date": "2019-03-01", "depth": 3, "layers": {"people": True, "countries": True, "artifacts": True, "sources": True, "claims": True}}
    for t in TEMPLATES.values():
        cy, params = t.build(sample)
        v = validate(cy, params=params)
        assert v.classification == "READ", t.name


def test_depth_is_capped():
    cy, _ = TEMPLATES["vendors_of"].build({"entity_id": "x", "depth": 99})
    assert "*1..6]" in cy


def test_neighbourhood_result_size_is_bounded():
    _, params = TEMPLATES["neighbourhood"].build({"entity_id": "x", "limit": 999999})
    assert params["limit"] == 1000
    _, params = TEMPLATES["neighbourhood"].build({"entity_id": "x", "limit": -1})
    assert params["limit"] == 1


def test_named_ownership_paths_filter_backing_simulation_provenance():
    sample = {
        "entity_id": "vendor", "root_id": "program", "home_country": "US",
    }
    for name in ("ownership_chain", "foreign_parent"):
        cypher, _ = TEMPLATES[name].build(sample)
        ownership_scope = cypher.split("OPTIONAL MATCH up=", 1)[1]
        assert "all(r IN relationships(up) WHERE" in ownership_scope
        assert "MATCH (rc:Claim {id:r.claim_id})" in ownership_scope
        assert "MATCH (ra:Artifact)-[:EVIDENCES]->(rc)" in ownership_scope
        assert "MATCH (:Artifact)-[re:EVIDENCES]->(rc)" in ownership_scope
        assert ownership_scope.index("$include_simulated") < ownership_scope.index(
            "RETURN",
        )
    foreign, _ = TEMPLATES["foreign_parent"].build(sample)
    seat_scope = foreign.split("MATCH (v)-[ps:PARENT_SEATED_IN]", 1)[1].split(
        "OPTIONAL MATCH up=", 1,
    )[0]
    assert "MATCH (rc:Claim {id:ps.claim_id})" in seat_scope
    assert "MATCH (ra:Artifact)-[:EVIDENCES]->(rc)" in seat_scope
    assert "MATCH (:Artifact)-[re:EVIDENCES]->(rc)" in seat_scope


def test_intent_matching():
    assert match_intent("for all of Sikorsky's vendors, highlight goods in purple and services in yellow") == "color_by_category"
    assert match_intent("highlight all entities that rely on manufacturing in country CN, include tier 2 and below") == "manufactures_in"
    assert match_intent("who owns GKN") == "ownership_chain"
    assert match_intent("show sole-source suppliers") == "sole_source"
