from illuminate.cypher.templates import TEMPLATES, match_intent
from illuminate.cypher.validator import validate


def test_all_templates_validate_as_reads():
    sample = {"entity_id": "ent_x", "root_id": "ent_root", "country": "CN", "date": "2019-03-01", "depth": 3, "layers": {"people": True, "countries": True, "artifacts": True}}
    for t in TEMPLATES.values():
        cy, params = t.build(sample)
        v = validate(cy, params=params)
        assert v.classification == "READ", t.name


def test_depth_is_capped():
    cy, _ = TEMPLATES["vendors_of"].build({"entity_id": "x", "depth": 99})
    assert "*1..6]" in cy


def test_intent_matching():
    assert match_intent("for all of Sikorsky's vendors, highlight goods in purple and services in yellow") == "color_by_category"
    assert match_intent("highlight all entities that rely on manufacturing in country CN, include tier 2 and below") == "manufactures_in"
    assert match_intent("who owns GKN") == "ownership_chain"
    assert match_intent("show sole-source suppliers") == "sole_source"
