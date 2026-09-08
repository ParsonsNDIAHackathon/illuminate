"""Artifacts, sources and claims are three canvas layers, not one. A source is an
Artifact that points at where data came from (a LittleSis org page, a registry entry,
a sanctions list); an artifact is a document in its own right; a claim is the
assertion the evidence supports."""
import json
import pytest
from types import SimpleNamespace

from illuminate import config
from illuminate.cypher.templates import TEMPLATES
from illuminate.graphio import layer_of
from illuminate.schema import SOURCE_KINDS
from illuminate.tools import handlers
from illuminate.tools.handlers import ToolContext, filter_simulated_subgraph


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


def test_workspace_simulation_opt_in_defaults_off_and_persists(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "_ws_path", lambda: tmp_path / "workspace.json")
    assert config.load_workspace().include_simulated is False

    workspace = config.load_workspace()
    workspace.include_simulated = True
    config.save_workspace(workspace)

    assert config.load_workspace().include_simulated is True


def test_operational_graph_projection_removes_scenario_nodes_and_edges():
    projected = filter_simulated_subgraph({
        "nodes": [
            {"id": "real", "props": {"simulated": False}},
            {"id": "sim", "props": {"simulated": True}},
        ],
        "edges": [
            {"id": "to-sim", "source": "real", "target": "sim", "props": {}},
            {"id": "sim-edge", "source": "real", "target": "real", "props": {"simulated": True}},
        ],
    }, include_simulated=False)

    assert [node["id"] for node in projected["nodes"]] == ["real"]
    assert projected["edges"] == []
    assert ToolContext().include_simulated is False

    connected = filter_simulated_subgraph({
        "nodes": [
            {"id": "root", "props": {}},
            {"id": "hidden-bridge", "props": {"simulated": True}},
            {"id": "derived-real", "props": {}},
        ],
        "edges": [
            {"id": "one", "source": "root", "target": "hidden-bridge", "props": {}},
            {"id": "two", "source": "hidden-bridge", "target": "derived-real", "props": {}},
        ],
    }, include_simulated=False, root_id="root")
    assert [node["id"] for node in connected["nodes"]] == ["root"]


@pytest.mark.asyncio
async def test_named_queries_bind_simulation_policy_and_custom_queries_fail_closed(monkeypatch):
    captured = {}

    async def read_graph(statement, params):
        captured.update(params)
        return [], SimpleNamespace(nodes=[], relationships=[]), {}

    monkeypatch.setattr(handlers.db, "read_graph", read_graph)
    named = await handlers.run_template(
        ToolContext(include_simulated=False),
        "vendors_of",
        {"entity_id": "program"},
    )
    custom = await handlers.run_cypher(
        ToolContext(include_simulated=False),
        "MATCH (e:Entity) RETURN e.name AS name",
    )

    assert named.ok
    assert captured["include_simulated"] is False
    assert not custom.ok
    assert "cannot be safely filtered" in custom.data["error"]


@pytest.mark.asyncio
async def test_neighbourhood_rows_match_filtered_subgraph(monkeypatch):
    async def read_graph(_statement, _params):
        return [{
            "nodes": [
                {"id": "root", "label": "Entity", "name": "Root", "props": {}},
                {"id": "scenario", "label": "Entity", "name": "Scenario", "props": {"simulated": True}},
            ],
            "relationships": [],
        }], SimpleNamespace(nodes=[], relationships=[]), {}

    monkeypatch.setattr(handlers.db, "read_graph", read_graph)
    result = await handlers.run_template(
        ToolContext(include_simulated=False),
        "neighbourhood",
        {"entity_id": "root"},
    )

    assert result.ok
    assert [node["id"] for node in result.data["rows"][0]["nodes"]] == ["root"]


@pytest.mark.asyncio
async def test_neighbourhood_opt_in_preserves_labels_and_simulated_root_fails_closed(monkeypatch):
    rows = [{
        "nodes": [
            {"id": "root", "label": "Entity", "name": "Scenario root", "props": {"simulated": True}},
            {"id": "vendor", "label": "Entity", "name": "Vendor", "props": {}},
        ],
        "relationships": [{
            "id": "scenario-edge", "type": "SUPPLIES", "source": "vendor",
            "target": "root", "props": {"simulated": True},
        }],
    }]

    async def read_graph(_statement, _params):
        return rows, SimpleNamespace(nodes=[], relationships=[]), {}

    monkeypatch.setattr(handlers.db, "read_graph", read_graph)
    enabled = await handlers.run_template(
        ToolContext(include_simulated=True),
        "neighbourhood",
        {"entity_id": "root"},
    )
    disabled = await handlers.run_template(
        ToolContext(include_simulated=False),
        "neighbourhood",
        {"entity_id": "root"},
    )

    model_payload = json.loads(enabled.for_model("run_template"))
    compact_nodes = model_payload["data"]["rows"][0]["nodes"]
    assert next(node for node in compact_nodes if node["id"] == "root")["simulated"] is True
    assert disabled.subgraph == {"nodes": [], "edges": []}
    assert disabled.data["rows"][0]["nodes"] == []
