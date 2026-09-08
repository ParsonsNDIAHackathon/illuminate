"""Artifacts, sources and claims are three canvas layers, not one. A source is an
Artifact that points at where data came from (a LittleSis org page, a registry entry,
a sanctions list); an artifact is a document in its own right; a claim is the
assertion the evidence supports."""
import json

from illuminate import config
from illuminate.cypher.templates import TEMPLATES
from illuminate.graphio import layer_of
from illuminate.schema import SOURCE_KINDS


def test_layer_of_splits_artifacts_by_kind():
    assert layer_of("Artifact", {"kind": "record", "title": "LittleSis: Raytheon Company"}) == "sources"
    assert layer_of("Artifact", {"kind": "registry", "title": "GLEIF LEI record X"}) == "sources"
    assert layer_of("Artifact", {}) == "sources", "kind defaults to record, the ArtifactRef default"
    for kind in ("filing", "news", "award", "web", "document"):
        assert layer_of("Artifact", {"kind": kind}) == "artifacts", kind
    assert layer_of("Claim", {"id": "clm_abc"}) == "claims"
    assert layer_of("Person", {}) == "people"
    assert layer_of("Entity", {"kind": "program"}) is None, "entities are always drawn"
    assert set(SOURCE_KINDS) == {"record", "registry"}


def _rels(layers):
    cy, _ = TEMPLATES["neighbourhood"].build({"entity_id": "x", "layers": layers})
    return cy.split("relationshipFilter:'")[1].split("'")[0].split("|")


def test_neighbourhood_rel_filter_follows_each_layer():
    base = _rels({"people": False})
    assert "EVIDENCES" not in base and "ASSERTS" not in base
    assert set(_rels({"people": False, "artifacts": True})) - set(base) == {"EVIDENCES", "ABOUT"}
    assert set(_rels({"people": False, "sources": True})) - set(base) == {"EVIDENCES", "ABOUT"}
    assert set(_rels({"people": False, "claims": True})) - set(base) == {"ASSERTS", "TARGETS", "EVIDENCES"}
    both = _rels({"people": False, "artifacts": True, "claims": True})
    assert both.count("EVIDENCES") == 1, "the filter is a set, however many layers share an edge"


def test_workspace_gains_new_layers_without_losing_choices(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_ws_path", lambda: tmp_path / "workspace.json")
    (tmp_path / "workspace.json").write_text(json.dumps({"layers": {"entities": True, "people": False, "countries": True, "artifacts": True, "categories": False}}))
    layers = config.load_workspace().layers
    assert layers["people"] is False and layers["countries"] is True and layers["artifacts"] is True
    assert layers["sources"] is False and layers["claims"] is False
    assert set(layers) == set(config.LAYER_DEFAULTS)
