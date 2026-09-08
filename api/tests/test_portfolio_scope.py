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
    assert f"[:SUPPLIES*1..{SUPPLY_SCOPE_MAX_DEPTH}]" in rows_query
    assert "min(length(path)) AS tier" in rows_query
    # What must stay supply-only is the *scoping* walk: an ownership hop there would admit
    # entities that do not supply the program. Ownership is still walked afterwards, per row,
    # to name the ultimate parent — that subquery returns one value and cannot change the row set.
    scoping = rows_query.split("OPTIONAL MATCH")[0]
    assert "OWNS" not in scoping and "ULTIMATE_PARENT_OF" not in scoping
    assert "SKIP $offset LIMIT $limit" in rows_query
    assert "WITH DISTINCT e RETURN count(e) AS n" in total_query
    assert params["root_id"] == "program_a"
    assert result["items"][0]["tier"] == 5
    assert result["total"] == 1205