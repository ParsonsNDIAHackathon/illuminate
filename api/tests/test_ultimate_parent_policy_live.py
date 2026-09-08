"""Behavioral ownership-policy checks against Neo4j when it is available."""
from __future__ import annotations

from uuid import uuid4

import pytest

from illuminate import db
from illuminate.report import ultimate_parents
from illuminate.routers import graph
from illuminate.tools import handlers
from illuminate.tools.handlers import ToolContext


@pytest.mark.asyncio
async def test_live_parent_selection_filters_roots_shortcuts_and_every_hop(monkeypatch):
    prefix = f"test_up_policy_{uuid4().hex}_"
    ids = {
        key: prefix + key
        for key in (
            "vendor_a", "parent_a", "sim_owner_a",
            "vendor_b", "mid_b", "root_b", "sim_shortcut_b",
            "vendor_c", "mid_c", "root_c", "program_c", "location_c",
            "claim_c", "artifact_c",
        )
    }
    names = {key: prefix + key.replace("_", " ") for key in ids}

    await db.close_driver()
    try:
        try:
            await db.read("RETURN 1 AS ok", timeout=3)
        except Exception:
            pytest.skip("neo4j not reachable")

        await db.write(
            """
            CREATE (va:Entity {id:$vendor_a, name:$vendor_a_name, kind:'organization'})
            CREATE (pa:Entity {id:$parent_a, name:$parent_a_name, kind:'organization'})
            CREATE (sa:Entity {id:$sim_owner_a, name:$sim_owner_a_name, kind:'organization', simulated:true})
            CREATE (pa)-[:OWNS {id:$owns_parent_a}]->(va)
            CREATE (sa)-[:OWNS {id:$owns_sim_a, simulated:true}]->(pa)

            CREATE (vb:Entity {id:$vendor_b, name:$vendor_b_name, kind:'organization'})
            CREATE (mb:Entity {id:$mid_b, name:$mid_b_name, kind:'organization'})
            CREATE (rb:Entity {id:$root_b, name:$root_b_name, kind:'organization'})
            CREATE (sb:Entity {id:$sim_shortcut_b, name:$sim_shortcut_b_name, kind:'organization', simulated:true})
            CREATE (rb)-[:OWNS {id:$owns_root_b}]->(mb)
            CREATE (mb)-[:OWNS {id:$owns_mid_b}]->(vb)
            CREATE (sb)-[:OWNS {id:$owns_shortcut_b, simulated:true}]->(vb)

            CREATE (vc:Entity {id:$vendor_c, name:$vendor_c_name, kind:'organization'})
            CREATE (mc:Entity {id:$mid_c, name:$mid_c_name, kind:'organization'})
            CREATE (rc:Entity {id:$root_c, name:$root_c_name, kind:'organization'})
            CREATE (pc:Entity {id:$program_c, name:$program_c_name, kind:'program'})
            CREATE (lc:Location {id:$location_c, name:'China', code:'CN'})
            CREATE (cc:Claim {id:$claim_c, simulated:false})
            CREATE (ac:Artifact {id:$artifact_c, simulated:false})
            CREATE (rc)-[:OWNS {id:$owns_root_c}]->(mc)
            CREATE (mc)-[:OWNS {id:$owns_mid_c, claim_id:$claim_c}]->(vc)
            CREATE (vc)-[:SUPPLIES {id:$supply_c}]->(pc)
            CREATE (vc)-[:PARENT_SEATED_IN {id:$seat_c, claim_id:$claim_c}]->(lc)
            CREATE (ac)-[:EVIDENCES {id:$evidence_c, simulated:true}]->(cc)
            """,
            {
                **ids,
                **{
                    f"{key}_name": value for key, value in names.items()
                    if key.startswith((
                        "vendor_", "parent_", "sim_owner_", "mid_", "root_",
                        "sim_shortcut_", "program_",
                    ))
                },
                "owns_parent_a": prefix + "owns_parent_a",
                "owns_sim_a": prefix + "owns_sim_a",
                "owns_root_b": prefix + "owns_root_b",
                "owns_mid_b": prefix + "owns_mid_b",
                "owns_shortcut_b": prefix + "owns_shortcut_b",
                "owns_root_c": prefix + "owns_root_c",
                "owns_mid_c": prefix + "owns_mid_c",
                "supply_c": prefix + "supply_c",
                "seat_c": prefix + "seat_c",
                "evidence_c": prefix + "evidence_c",
            },
        )

        live_a = await ultimate_parents(ids["vendor_a"], include_simulated=False)
        opted_a = await ultimate_parents(ids["vendor_a"], include_simulated=True)
        assert [item["id"] for item in live_a] == [ids["parent_a"]]
        assert [item["id"] for item in opted_a] == [ids["sim_owner_a"]]
        assert opted_a[0]["simulated"] is True

        live_b = await ultimate_parents(ids["vendor_b"], include_simulated=False)
        opted_b = await ultimate_parents(ids["vendor_b"], include_simulated=True)
        assert [item["id"] for item in live_b] == [ids["root_b"]]
        assert [item["id"] for item in opted_b] == [
            ids["sim_shortcut_b"], ids["root_b"],
        ]

        assert await ultimate_parents(ids["vendor_c"], include_simulated=False) == []
        opted_c = await ultimate_parents(ids["vendor_c"], include_simulated=True)
        assert [item["id"] for item in opted_c] == [ids["root_c"]]
        assert opted_c[0]["claim_ids"] == [ids["claim_c"]]
        assert opted_c[0]["evidence_simulated"] is True
        assert opted_c[0]["simulated"] is True

        live_template = await handlers.run_template(
            ToolContext(include_simulated=False),
            "ownership_chain",
            {"entity_id": ids["vendor_c"]},
        )
        opted_template = await handlers.run_template(
            ToolContext(include_simulated=True),
            "ownership_chain",
            {"entity_id": ids["vendor_c"]},
        )
        assert live_template.ok and opted_template.ok
        assert not [
            row.get("parent_id") for row in live_template.data["rows"]
            if row.get("parent_id")
        ]
        assert ids["mid_c"] not in {
            node["id"] for node in live_template.subgraph["nodes"]
        }
        assert prefix + "owns_mid_c" not in {
            edge["id"] for edge in live_template.subgraph["edges"]
        }
        live_owner_styles = [
            op for op in live_template.style_ops
            if op.get("label") == "Owners / parents"
        ]
        assert live_owner_styles and live_owner_styles[0].get("ids") == []

        assert ids["root_c"] in {
            row.get("parent_id") for row in opted_template.data["rows"]
        }
        assert ids["mid_c"] in {
            node["id"] for node in opted_template.subgraph["nodes"]
        }
        assert prefix + "owns_mid_c" in {
            edge["id"] for edge in opted_template.subgraph["edges"]
        }
        opted_owner_styles = [
            op for op in opted_template.style_ops
            if op.get("label") == "Owners / parents"
        ]
        assert ids["root_c"] in opted_owner_styles[0]["ids"]

        live_foreign = await handlers.run_template(
            ToolContext(include_simulated=False),
            "foreign_parent",
            {"root_id": ids["program_c"], "home_country": "US"},
        )
        opted_foreign = await handlers.run_template(
            ToolContext(include_simulated=True),
            "foreign_parent",
            {"root_id": ids["program_c"], "home_country": "US"},
        )
        assert live_foreign.ok and opted_foreign.ok
        assert live_foreign.data["rows"] == []
        assert live_foreign.subgraph == {"nodes": [], "edges": []}
        assert all(not op.get("ids") for op in live_foreign.style_ops)
        assert any(
            (row.get("up") or {}).get("path_edges")
            for row in opted_foreign.data["rows"]
        )
        assert ids["mid_c"] in {
            node["id"] for node in opted_foreign.subgraph["nodes"]
        }
        assert prefix + "owns_mid_c" in {
            edge["id"] for edge in opted_foreign.subgraph["edges"]
        }

        monkeypatch.setattr(
            graph, "load_workspace",
            lambda: type("Workspace", (), {"include_simulated": True})(),
        )
        live_list = await graph.entities(
            q=names["vendor_a"], kind="organization", flagged=None, root_id=None,
            include_simulated=False, limit=10, offset=0,
        )
        opted_list = await graph.entities(
            q=names["vendor_a"], kind="organization", flagged=None, root_id=None,
            include_simulated=True, limit=10, offset=0,
        )
        assert live_list["items"][0]["parent"] == names["parent_a"]
        assert opted_list["items"][0]["parent"] == names["sim_owner_a"]
    finally:
        try:
            await db.write(
                "MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n",
                {"prefix": prefix},
            )
        except Exception:
            pass
        await db.close_driver()