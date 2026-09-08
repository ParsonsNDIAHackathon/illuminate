import pytest
from unittest.mock import AsyncMock

from illuminate.routers import graph
from illuminate import report as report_module
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
    assert "all(n IN nodes(path) WHERE coalesce(n.simulated,false)=false)" in enrichment_query
    assert "all(r IN relationships(path) WHERE" in enrichment_query
    assert "MATCH (rc:Claim {id:r.claim_id})" in enrichment_query
    assert "MATCH (owner:Entity)-[incoming:OWNS|ULTIMATE_PARENT_OF]->(up)" in enrichment_query
    assert "coalesce(owner.simulated,false)=false" in enrichment_query
    assert enrichment_query.index("$include_simulated") < enrichment_query.index(
        "ORDER BY length(path)",
    )
    assert "SKIP $offset LIMIT $limit" in rows_query
    assert "WITH DISTINCT e RETURN count(e) AS n" in total_query
    assert params["root_id"] == "program_a"
    assert result["items"][0]["tier"] == 5
    assert result["total"] == 1205

@pytest.mark.asyncio
async def test_operational_entity_list_excludes_simulations_unless_workspace_opts_in(monkeypatch):
    queries = []

    async def read(query: str, params: dict):
        queries.append((query, params))
        return [{"n": 0}] if "RETURN count(e) AS n" in query else []

    monkeypatch.setattr(graph.db, "read", read)
    monkeypatch.setattr(
        graph, "load_workspace", lambda: type("Workspace", (), {"include_simulated": False})()
    )
    await graph.entities()
    assert all("$include_simulated" in query for query, _ in queries)
    assert all(params["include_simulated"] is False for _, params in queries)

    queries.clear()
    monkeypatch.setattr(
        graph, "load_workspace", lambda: type("Workspace", (), {"include_simulated": True})()
    )
    await graph.entities()
    assert all(params["include_simulated"] is True for _, params in queries)

@pytest.mark.asyncio
async def test_location_and_artifact_aggregates_apply_workspace_boundary(monkeypatch):
    queries = []

    async def read(query, params):
        queries.append((query, params))
        return []

    monkeypatch.setattr(graph.db, "read", read)
    monkeypatch.setattr(
        graph, "load_workspace", lambda: type("Workspace", (), {"include_simulated": False})()
    )

    await graph.locations()
    await graph.artifacts()

    assert all("$include_simulated" in query for query, _ in queries)
    assert all(params["include_simulated"] is False for _, params in queries)
    assert any("coalesce(r.simulated,false)=false" in query for query, _ in queries)
    assert any("coalesce(c.simulated,false)=false" in query for query, _ in queries)

@pytest.mark.asyncio
async def test_bulk_report_projection_does_not_queue_refresh(monkeypatch):
    monkeypatch.setattr(
        graph, "build_report",
        AsyncMock(return_value={"identity": {"id": "vendor", "kind": "organization"}}),
    )
    monkeypatch.setattr(graph.decisions, "history", AsyncMock(return_value=[]))
    monkeypatch.setattr(graph.worker, "enqueue", AsyncMock())
    monkeypatch.setattr(
        graph, "load_workspace", lambda: type("Workspace", (), {"include_simulated": False})()
    )

    result = await graph.report("vendor", refresh=False, user="operator")

    graph.worker.enqueue.assert_not_awaited()
    assert result["refresh"]["status"] == "not_requested"

@pytest.mark.asyncio
async def test_report_aggregate_queries_apply_live_only_boundary(monkeypatch):
    queries = []

    async def read(query, params):
        queries.append((query, params))
        if "RETURN count(*) AS n" in query:
            return [{"n": 0}]
        if "RETURN count(a) AS n" in query:
            return [{"n": 0, "total": None}]
        if "AS evidence" in query:
            return [{"evidence": []}]
        return []

    monkeypatch.setattr(report_module.db, "read", read)
    await report_module.supply_position("vendor", "program")

    assert len(queries) == 5
    assert all("$include_simulated" in query for query, _ in queries)
    assert all(params["include_simulated"] is False for _, params in queries)

@pytest.mark.asyncio
async def test_company_report_returns_immediate_background_refresh_status(monkeypatch):
    report_data = {
        "identity": {"id": "vendor", "name": "Vendor", "kind": "organization"},
    }
    build = AsyncMock(return_value=report_data)
    queued = type(
        "Job", (), {
            "id": "job_refresh", "status": "queued", "created_at": 123.0,
        },
    )()
    monkeypatch.setattr(graph, "build_report", build)
    monkeypatch.setattr(graph.decisions, "history", AsyncMock(return_value=[]))
    monkeypatch.setattr(graph.worker, "enqueue", AsyncMock(return_value=queued))
    monkeypatch.setattr(graph.worker, "jobs", {})
    monkeypatch.setattr(
        graph, "load_workspace", lambda: type("Workspace", (), {"include_simulated": False})()
    )

    result = await graph.report("vendor", root_id="program", user="operator")

    build.assert_awaited_once_with("vendor", "program", include_simulated=False)
    graph.worker.enqueue.assert_awaited_once_with(
        "vendor", user="operator", requested_by="report"
    )
    assert result["refresh_status"]["status"] == "queued"
    assert result["refresh_status"]["job_id"] == "job_refresh"
    assert result["source_mode"] == "live"
