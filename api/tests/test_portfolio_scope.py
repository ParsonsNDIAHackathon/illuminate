import pytest

from illuminate.routers import graph
from illuminate.schema import SUPPLY_SCOPE_MAX_DEPTH


@pytest.mark.asyncio
async def test_mission_portfolio_is_supply_only_paginated_and_mission_relative(monkeypatch):
    queries: list[tuple[str, dict]] = []

    async def read(query: str, params: dict):
        queries.append((query, params))
        if "RETURN count(e) AS n" in query:
            return [{"n": 1205}]
        return [{
            "id": "vendor_tier_5",
            "name": "Tier Five Vendor",
            "kind": "organization",
            "tier": 5,
            "simulated": False,
        }]

    monkeypatch.setattr(graph.db, "read", read)
    result = await graph.entities(
        q=None,
        kind="organization",
        flagged=None,
        root_id="program_a",
        limit=1000,
        offset=0,
    )

    rows_query, params = queries[0]
    total_query, _ = queries[1]
    membership_query, enrichment_query = rows_query.split("OPTIONAL MATCH", 1)
    assert f"[:SUPPLIES*1..{SUPPLY_SCOPE_MAX_DEPTH}]" in membership_query
    assert "min(length(path)) AS tier" in membership_query
    assert "OWNS" not in membership_query and "ULTIMATE_PARENT_OF" not in membership_query
    assert "OWNS|ULTIMATE_PARENT_OF" in enrichment_query
    assert "SKIP $offset LIMIT $limit" in rows_query
    assert "WITH DISTINCT e RETURN count(e) AS n" in total_query
    assert params["root_id"] == "program_a"
    assert result["items"][0]["tier"] == 5
    assert result["total"] == 1205