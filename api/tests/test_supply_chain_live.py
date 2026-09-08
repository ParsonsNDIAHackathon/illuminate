"""Bounded supply-chain integration checks against Neo4j when available."""
import pytest

from illuminate import db
from illuminate.supply_chain import (
    MAX_CAPABILITIES_PER_DEPENDENCY,
    MAX_COUNTRIES_PER_CONTROL,
    MAX_MANUFACTURING_PER_DEPENDENCY,
    MAX_ROLES_PER_SUPPLIER,
    get_supply_chain_analysis,
)


@pytest.mark.asyncio
async def test_high_degree_contexts_are_bounded_and_report_nondeterministic_selection():
    prefix = "test_sc_bound_"
    await db.close_driver()
    try:
        try:
            await db.read("RETURN 1 AS ok", timeout=3)
        except Exception:
            pytest.skip("neo4j not reachable")
        evidence = {
            "source": "bounded integration test", "retrieved_at": "2025-01-01T00:00:00Z",
            "confidence": 1.0, "status": "committed",
        }
        await db.write(
            "CREATE (root:Entity {id:$root,name:'Bound Root'}) "
            "CREATE (supplier:Entity {id:$supplier,name:'Bound Supplier'}) "
            "CREATE (supplier)-[:SUPPLIES {id:$supply_id,source:$source,retrieved_at:$retrieved_at,"
            "confidence:$confidence,status:$status}]->(root)",
            {"root": prefix + "root", "supplier": prefix + "supplier",
             "supply_id": prefix + "supply", **evidence},
        )
        for relationship, target_label, count in (
            ("PROVIDES", "Category", MAX_CAPABILITIES_PER_DEPENDENCY + 1),
            ("MANUFACTURES_IN", "Location", MAX_MANUFACTURING_PER_DEPENDENCY + 1),
        ):
            await db.write(
                f"MATCH (s:Entity {{id:$supplier}}) UNWIND range(0,$count-1) AS i "
                f"CREATE (n:{target_label} {{id:$prefix+toString(i),name:$prefix+toString(i),code:'GB'}}) "
                f"CREATE (s)-[r:{relationship}]->(n) "
                "SET r.id=$prefix+toString(i),r.source=$source,r.retrieved_at=$retrieved_at,"
                "r.confidence=$confidence,r.status=$status",
                {"supplier": prefix + "supplier", "count": count,
                 "prefix": prefix + relationship.lower() + "_", **evidence},
            )
        await db.write(
            "MATCH (s:Entity {id:$supplier}) UNWIND range(0,$count-1) AS i "
            "CREATE (p:Person {id:$prefix+toString(i),name:$prefix+toString(i)}) "
            "CREATE (p)-[r:HELD_ROLE]->(s) "
            "SET r.id=$prefix+toString(i),r.source=$source,r.retrieved_at=$retrieved_at,"
            "r.confidence=$confidence,r.status=$status,r.current=true",
            {"supplier": prefix + "supplier", "count": MAX_ROLES_PER_SUPPLIER + 1,
             "prefix": prefix + "role_", **evidence},
        )
        await db.write(
            "MATCH (s:Entity {id:$supplier}) CREATE (c:Entity {id:$controller,name:'Controller'}) "
            "CREATE (c)-[o:OWNS]->(s) SET o.id=$owns,o.source=$source,o.retrieved_at=$retrieved_at,"
            "o.confidence=$confidence,o.status=$status "
            "WITH c UNWIND range(0,$count-1) AS i "
            "CREATE (l:Location {id:$prefix+toString(i),name:$prefix+toString(i),code:'GB'}) "
            "CREATE (c)-[r:INCORPORATED_IN]->(l) "
            "SET r.id=$prefix+toString(i),r.source=$source,r.retrieved_at=$retrieved_at,"
            "r.confidence=$confidence,r.status=$status",
            {"supplier": prefix + "supplier", "controller": prefix + "controller",
             "owns": prefix + "owns", "count": MAX_COUNTRIES_PER_CONTROL + 1,
             "prefix": prefix + "country_", **evidence},
        )
        result = await get_supply_chain_analysis(prefix + "root")
        assert result is not None
        for key in ("capabilities", "manufacturing", "roles", "controls"):
            assert result.completeness[key]["truncated"] is True
            assert result.completeness[key]["selection_deterministic"] is False
        assert result.completeness["capabilities"]["returned"] <= MAX_CAPABILITIES_PER_DEPENDENCY
        assert result.completeness["manufacturing"]["returned"] <= MAX_MANUFACTURING_PER_DEPENDENCY
        assert result.completeness["roles"]["returned"] <= MAX_ROLES_PER_SUPPLIER
        assert result.completeness["controls"]["returned"] <= MAX_COUNTRIES_PER_CONTROL
    finally:
        try:
            await db.write(
                "MATCH (n) WHERE n.id STARTS WITH $prefix DETACH DELETE n", {"prefix": prefix}
            )
        except Exception:
            pass
        await db.close_driver()