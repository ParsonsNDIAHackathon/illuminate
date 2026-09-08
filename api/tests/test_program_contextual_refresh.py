"""Program creation schedules bounded contextual refresh without delaying writes."""
from types import SimpleNamespace

from illuminate.enrichment import worker as worker_mod
from illuminate.tools import handlers
from illuminate.tools.handlers import ToolContext


async def _none(*args, **kwargs):
    return None


async def _executed(*args, **kwargs):
    return SimpleNamespace(status="executed", request_id="req_1", reason=None,
                           result={"counters": {"nodes_created": 1}})


async def _subgraph(*args, **kwargs):
    return SimpleNamespace(subgraph={"nodes": [], "edges": []})


async def test_created_program_without_keywords_reports_procurement_not_applicable(monkeypatch):
    queued = []

    async def enqueue(entity_id, connectors=None, user="local", requested_by="ui"):
        queued.append((entity_id, connectors, user, requested_by))
        return worker_mod.Job("job_context", entity_id, "Program", connectors or [])

    monkeypatch.setattr(handlers, "find_entity", _none)
    monkeypatch.setattr(handlers, "fuzzy_candidates", _none)
    monkeypatch.setattr(handlers, "validate", lambda statement, params: SimpleNamespace(statement=statement))
    monkeypatch.setattr(handlers.gate, "request", _executed)
    monkeypatch.setattr(handlers, "expand_subgraph", _subgraph)
    monkeypatch.setattr(worker_mod.worker, "enqueue", enqueue)

    result = await handlers.propose_entity(ToolContext(source="chat", user="analyst"), "New Program", kind="program")

    assert result.ok
    assert result.data["contextual_refresh"]["status"] == "queued"
    assert result.data["contextual_refresh"]["job_id"] == "job_context"
    assert queued[0][1] == ["gdelt", "openstreetmap", "far", "epss"]
    assert queued[0][2:] == ("analyst", "chat")
    assert "usaspending" in result.data["contextual_refresh"]["not_applicable"]


async def test_created_program_with_keywords_queues_live_procurement(monkeypatch):
    queued = []

    async def enqueue(entity_id, connectors=None, user="local", requested_by="ui"):
        queued.append(connectors)
        return worker_mod.Job("job_procurement", entity_id, "Program", connectors or [])

    monkeypatch.setattr(handlers, "find_entity", _none)
    monkeypatch.setattr(handlers, "fuzzy_candidates", _none)
    monkeypatch.setattr(handlers, "validate", lambda statement, params: SimpleNamespace(statement=statement))
    monkeypatch.setattr(handlers.gate, "request", _executed)
    monkeypatch.setattr(handlers, "expand_subgraph", _subgraph)
    monkeypatch.setattr(worker_mod.worker, "enqueue", enqueue)

    result = await handlers.propose_entity(
        ToolContext(source="chat", user="analyst"),
        "New Program",
        kind="program",
        keywords=["program designation"],
    )

    assert result.ok
    assert queued[0] == ["usaspending", "gdelt", "openstreetmap", "far", "epss"]


async def test_program_create_reports_queue_failure_without_undoing_write(monkeypatch):
    async def enqueue(*args, **kwargs):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(handlers, "find_entity", _none)
    monkeypatch.setattr(handlers, "fuzzy_candidates", _none)
    monkeypatch.setattr(handlers, "validate", lambda statement, params: SimpleNamespace(statement=statement))
    monkeypatch.setattr(handlers.gate, "request", _executed)
    monkeypatch.setattr(handlers, "expand_subgraph", _subgraph)
    monkeypatch.setattr(worker_mod.worker, "enqueue", enqueue)

    result = await handlers.propose_entity(ToolContext(), "Queue Failure Program", kind="program")

    assert result.ok
    assert result.data["contextual_refresh"]["status"] == "unavailable"
    assert result.data["contextual_refresh"]["action"]