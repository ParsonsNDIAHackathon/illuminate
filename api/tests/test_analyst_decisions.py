import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from illuminate.enrichment import decisions
from illuminate.main import app
from illuminate.routers import claims as claims_router


class _Record:
    def __init__(self, value):
        self.value = value

    def data(self):
        return self.value


class _Result:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, _limit):
        return [_Record(row) for row in self.rows]

    async def consume(self):
        return None


class _Tx:
    def __init__(self, handler):
        self.handler = handler

    async def run(self, query, params):
        return _Result(await self.handler(query, params))


def _transaction_runner(handler, lock=None):
    async def run(work, timeout=None):
        if lock is None:
            return await work(_Tx(handler))
        async with lock:
            return await work(_Tx(handler))
    return run


@pytest.mark.parametrize("disposition", sorted(decisions.DISPOSITIONS))
async def test_all_bounded_dispositions_are_accepted_with_attribution(monkeypatch, disposition):
    captured = {}

    async def build_report(entity_id, program_id):
        return {"risk": {"categories": [{"id": "ownership", "factors": [{"rule_id": "ownership"}]}]}}

    async def record(entity_id, **kwargs):
        captured.update(entity_id=entity_id, **kwargs)
        return {"id": "ade_1", **kwargs}

    monkeypatch.setattr(claims_router, "build_report", build_report)
    monkeypatch.setattr(claims_router.decisions, "record", record)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/claims/entities/ent_1/decisions",
            headers={"X-User": "analyst-7"},
            json={
                "disposition": disposition,
                "rationale": "Evidence needs documented follow-up.",
                "owner": "Supply Risk Team",
                "due_date": "2026-10-01",
                "program_id": "program_1",
                "finding_ids": ["finding:risk:ownership"],
                "evidence_refs": ["clm_1", "art_1"],
                "expected_version": 2,
            },
        )
    assert response.status_code == 201
    assert captured["actor"] == "analyst-7"
    assert captured["entity_id"] == "ent_1"
    assert captured["disposition"] == disposition


@pytest.mark.parametrize(
    "body",
    [
        {"disposition": "disqualify", "rationale": "Not a permitted action.", "owner": "Team", "finding_ids": ["finding:risk:test"]},
        {"disposition": "monitor", "rationale": "", "owner": "Team", "finding_ids": ["finding:risk:test"]},
        {"disposition": "monitor", "rationale": "Watch.", "owner": "", "finding_ids": ["finding:risk:test"]},
        {"disposition": "monitor", "rationale": "Watch.", "owner": "Team", "due_date": "2026-02-31", "finding_ids": ["finding:risk:test"]},
        {"disposition": "monitor", "rationale": "Watch.", "owner": "Team", "finding_ids": []},
    ],
)
async def test_decision_contract_rejects_unbounded_or_unaccountable_actions(body):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/claims/entities/ent_1/decisions", json=body)
    assert response.status_code == 422


async def test_record_is_append_only_and_propagates_simulation(monkeypatch):
    state = {"events": [], "simulated": True}

    async def handle(query, params):
        if "RETURN e.id AS id" in query and "current_version" in query:
            return [{
                "id": "ent_1", "simulated": state["simulated"],
                "current_version": max((item["version"] for item in state["events"]), default=0),
                "current_sequence": len(state["events"]),
            }]
        if "CREATE (decision:AnalystDecision" in query:
            event = {
                "id": params["event_id"], "entity_id": params["entity_id"],
                "disposition": params["disposition"], "rationale": params["rationale"],
                "owner": params["owner"], "actor": params["actor"],
                "decided_at": params["decided_at"], "version": params["version"],
                "sequence": params["sequence"],
                "simulated": params["simulated"], "finding_ids": params["finding_ids"],
                "evidence_refs": params["evidence_refs"],
            }
            state["events"].append(event)
            return [{"decision": event}]
        return []

    monkeypatch.setattr(decisions.db, "transactional_write", _transaction_runner(handle))
    first = await decisions.record(
        "ent_1", disposition="investigate", rationale="Validate the source.",
        owner="Analyst A", due_date=None, actor="reviewer", expected_version=0,
    )
    second = await decisions.record(
        "ent_1", disposition="monitor", rationale="Review monthly.",
        owner="Analyst B", due_date=None, actor="reviewer", expected_version=1,
    )
    assert [first["version"], second["version"]] == [1, 2]
    assert [item["disposition"] for item in state["events"]] == ["investigate", "monitor"]
    assert all(item["simulated"] is True for item in state["events"])


async def test_concurrent_updates_have_one_version_winner(monkeypatch):
    state = {"version": 0}
    lock = asyncio.Lock()

    async def handle(query, params):
        if "RETURN e.id AS id" in query and "current_version" in query:
            return [{
                "id": "ent_1", "simulated": False, "current_version": state["version"],
                "current_sequence": state["version"],
            }]
        if "CREATE (decision:AnalystDecision" in query:
            state["version"] += 1
            return [{"decision": {"id": params["event_id"], "version": state["version"]}}]
        return []

    monkeypatch.setattr(decisions.db, "transactional_write", _transaction_runner(handle, lock))
    calls = [
        decisions.record(
            "ent_1", disposition="monitor", rationale="Continue review.",
            owner="Team", due_date=None, actor="analyst", expected_version=0,
        )
        for _ in range(2)
    ]
    results = await asyncio.gather(*calls, return_exceptions=True)
    assert sum(isinstance(item, ValueError) for item in results) == 1
    assert sum(isinstance(item, dict) for item in results) == 1
    assert state["version"] == 1


async def test_history_keeps_claim_reviews_and_all_decision_versions(monkeypatch):
    async def read(query, params):
        return [{
            "decisions": [
                {"id": "ade_1", "version": 1, "disposition": "investigate", "decided_at": "2026-09-01T00:00:00Z"},
                {"id": "ade_2", "version": 2, "disposition": "monitor", "decided_at": "2026-09-03T00:00:00Z"},
            ],
            "reviews": [
                {"id": "cre_1", "claim_id": "clm_1", "to_status": "committed", "decided_at": "2026-09-02T00:00:00Z"},
            ],
        }]

    monkeypatch.setattr(decisions.db, "read", read)
    history = await decisions.history("ent_1")
    assert history["current"]["id"] == "ade_2"
    assert [event["id"] for event in history["events"]] == ["ade_2", "cre_1", "ade_1"]
    assert {event["kind"] for event in history["events"]} == {"analyst_decision", "claim_review"}


async def test_current_decision_is_scoped_to_the_active_program(monkeypatch):
    async def read(query, params):
        return [{
            "decisions": [
                {"id": "ade_a", "version": 1, "program_id": "program_a", "decided_at": "2026-09-01T00:00:00Z"},
                {"id": "ade_b", "version": 2, "program_id": "program_b", "decided_at": "2026-09-02T00:00:00Z"},
            ],
            "reviews": [],
        }]

    monkeypatch.setattr(decisions.db, "read", read)
    assert (await decisions.history("ent_1", program_id="program_a"))["current"]["id"] == "ade_a"
    assert (await decisions.history("ent_1", program_id="program_b"))["current"]["id"] == "ade_b"


async def test_unrelated_program_or_evidence_is_rejected_before_event_creation(monkeypatch):
    created = False

    async def handle(query, params):
        nonlocal created
        if "current_version" in query:
            return [{"id": "ent_1", "simulated": False, "current_version": 0, "current_sequence": 0}]
        if "OPTIONAL MATCH path=" in query:
            return [{"id": "program_other", "simulated": False, "related": False}]
        if "CREATE (decision:AnalystDecision" in query:
            created = True
        return []

    monkeypatch.setattr(decisions.db, "transactional_write", _transaction_runner(handle))
    with pytest.raises(ValueError, match="supply-chain context"):
        await decisions.record(
            "ent_1", disposition="monitor", rationale="Review.",
            owner="Team", due_date=None, actor="analyst", program_id="program_other",
            finding_ids=["finding:risk:test"], expected_version=0,
        )
    assert created is False


async def test_api_rejects_a_finding_not_present_in_the_vendor_report(monkeypatch):
    called = False

    async def build_report(entity_id, program_id):
        return {"risk": {"categories": [{"id": "ownership", "factors": [{"rule_id": "ownership.foreign-parent.v1"}]}]}}

    async def record(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(claims_router, "build_report", build_report)
    monkeypatch.setattr(claims_router.decisions, "record", record)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/claims/entities/ent_1/decisions", json={
            "disposition": "monitor", "rationale": "Watch this factor.", "owner": "Team",
            "finding_ids": ["finding:risk:invented.factor.v1"],
        })
    assert response.status_code == 422
    assert called is False