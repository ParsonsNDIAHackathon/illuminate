import asyncio

import pytest
from httpx import ASGITransport, AsyncClient

from illuminate.enrichment import claims
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


@pytest.mark.parametrize(
    "path",
    [
        "/api/claims?limit=0",
        f"/api/claims?limit={claims_router.MAX_PAGE_LIMIT + 1}",
        "/api/claims?status=unknown",
        "/api/claims/source-records?limit=0",
        f"/api/claims/source-records?limit={claims_router.MAX_PAGE_LIMIT + 1}",
    ],
)
async def test_claim_list_boundaries_reject_invalid_requests(path):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)
    assert response.status_code == 422


async def test_claim_list_accepts_bounded_filters(monkeypatch):
    received = {}

    async def list_claims(status, entity_id, limit, claim_id):
        received.update(status=status, entity_id=entity_id, limit=limit, claim_id=claim_id)
        return []

    monkeypatch.setattr(claims_router.claims, "list_claims", list_claims)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/claims",
            params={"status": "staged", "entity_id": "ent_1", "limit": claims_router.MAX_PAGE_LIMIT},
        )
    assert response.status_code == 200
    assert received == {
        "status": "staged",
        "entity_id": "ent_1",
        "limit": claims_router.MAX_PAGE_LIMIT,
        "claim_id": None,
    }


@pytest.mark.parametrize(
    ("action", "error", "expected_status"),
    [
        ("commit", KeyError("missing"), 404),
        ("reject", KeyError("missing"), 404),
        ("commit", ValueError("invalid transition"), 409),
        ("reject", ValueError("invalid transition"), 409),
    ],
)
async def test_claim_decisions_explain_missing_and_invalid_transitions(
    monkeypatch, action, error, expected_status
):
    async def fail(*args, **kwargs):
        raise error

    async def no_endpoints(*_args, **_kwargs):
        return []

    monkeypatch.setattr(claims_router.claims, action, fail)
    monkeypatch.setattr(claims_router.claims, "endpoints", no_endpoints)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(f"/api/claims/clm_1/{action}", json={})
    assert response.status_code == expected_status
    assert response.json()["detail"]


async def test_reject_staged_claim_and_repeat_is_idempotent(monkeypatch):
    state = {"status": "staged"}
    queries = []

    async def handle(query, params):
        queries.append((query, params))
        if "RETURN c.status AS status" in query:
            return [{"status": state["status"]}]
        if "c.status='rejected'" in query:
            state["status"] = "rejected"
        return []

    monkeypatch.setattr(
        claims.db,
        "transactional_write",
        _transaction_runner(handle),
    )

    assert await claims.reject("clm_1", "not supported") == "rejected"
    assert await claims.reject("clm_1", "retry") == "rejected"
    assert state["status"] == "rejected"
    assert sum("c.status='rejected'" in query for query, _params in queries) == 1
    assert sum("c.decision_version=coalesce" in query for query, _params in queries) == 1
    event_writes = [(query, params) for query, params in queries if "CREATE (review:ClaimReview" in query]
    assert len(event_writes) == 1
    assert event_writes[0][1]["actor"] == "system"


@pytest.mark.parametrize("status", ["committed", "unexpected"])
async def test_reject_cannot_rewrite_non_staged_claim(monkeypatch, status):
    async def handle(query, params):
        if "RETURN c.status AS status" in query:
            return [{"status": status}]
        raise AssertionError("invalid transition must not update claim status")

    monkeypatch.setattr(
        claims.db,
        "transactional_write",
        _transaction_runner(handle),
    )

    with pytest.raises(ValueError, match="cannot be rejected"):
        await claims.reject("clm_1")


async def test_reject_missing_claim_fails_without_write(monkeypatch):
    async def handle(query, params):
        return []

    monkeypatch.setattr(
        claims.db,
        "transactional_write",
        _transaction_runner(handle),
    )

    with pytest.raises(KeyError):
        await claims.reject("missing")


async def test_concurrent_commit_and_reject_have_one_terminal_winner(monkeypatch):
    state = {"status": "staged", "direct_fact_written": False}
    transaction_lock = asyncio.Lock()
    commit_locked = asyncio.Event()
    release_commit = asyncio.Event()

    async def handle(query, params):
        if "RETURN c{.*} AS c" in query:
            commit_locked.set()
            await release_commit.wait()
            return [{
                "c": {
                    "status": state["status"],
                    "predicate": "note",
                    "source": "test",
                    "rel_props": "{}",
                },
                "sid": "ent_1",
                "oid": None,
            }]
        if "RETURN c.status AS status" in query:
            return [{"status": state["status"]}]
        if "c.status='committed'" in query:
            state["status"] = "committed"
        if "c.status='rejected'" in query:
            state["status"] = "rejected"
        if "MERGE (s)-[r:" in query or "_claim_id" in query:
            state["direct_fact_written"] = True
        return []

    monkeypatch.setattr(
        claims.db,
        "transactional_write",
        _transaction_runner(handle, transaction_lock),
    )

    commit_task = asyncio.create_task(claims.commit("clm_1"))
    await commit_locked.wait()
    reject_task = asyncio.create_task(claims.reject("clm_1"))
    await asyncio.sleep(0)
    assert not reject_task.done()
    release_commit.set()

    assert await commit_task == "committed"
    with pytest.raises(ValueError, match="cannot be rejected"):
        await reject_task
    assert state == {"status": "committed", "direct_fact_written": False}

async def test_committed_observation_refreshes_materialized_fact_without_new_decision(monkeypatch):
    materialized = []
    claim_updates = []

    async def handle(query, params):
        if "RETURN c{.*} AS c" in query:
            return [{
                "c": {
                    "status": "committed",
                    "predicate": "SUPPLIES",
                    "source": "usaspending",
                    "retrieval_status": "live",
                    "retrieval_mode": "operational_live",
                    "latest_retrieved_at": "2026-09-08T12:00:00Z",
                    "rel_props": '{"amount": 2500000, "award_count": 4, "sole_source": true}',
                    "merge_keys": "[]",
                    "decision_version": 3,
                    "decision_note": "approved previously",
                },
                "sid": "supplier",
                "oid": "program",
            }]
        if "RETURN a.url AS url" in query:
            return []
        if "MERGE (s)-[r:SUPPLIES" in query:
            materialized.append(params)
        if "MATCH (c:Claim {id:$id}) SET" in query:
            claim_updates.append((query, params))
        return []

    monkeypatch.setattr(claims.db, "transactional_write", _transaction_runner(handle))

    assert await claims.commit("stable-observation", refresh_materialization=True) == "committed"
    assert materialized[0]["rp"]["amount"] == 2500000
    assert materialized[0]["rp"]["award_count"] == 4
    assert materialized[0]["rp"]["sole_source"] is True
    assert materialized[0]["prov"]["retrieval_status"] == "live"
    assert materialized[0]["prov"]["retrieval_mode"] == "operational_live"
    assert len(claim_updates) == 1
    assert "decision_version" not in claim_updates[0][0]
    assert "decision_note" not in claim_updates[0][0]


async def test_retrying_old_attribute_claim_cannot_undo_newer_commit(monkeypatch):
    records = {
        "claim-a": {
            "status": "staged", "predicate": "attr:legal_name",
            "object_value": "Old name", "source": "test",
        },
        "claim-b": {
            "status": "staged", "predicate": "attr:legal_name",
            "object_value": "New name", "source": "test",
        },
    }
    entity = {"legal_name": None, "legal_name_claim_id": None}
    reviews = []

    async def handle(query, params):
        if "RETURN c{.*} AS c" in query:
            claim = records[params["id"]]
            return [{"c": dict(claim), "sid": "ent-1", "oid": None}]
        if "RETURN a.url AS url" in query:
            return []
        if "SET s.legal_name" in query:
            guarded = (
                "WHERE s.legal_name_claim_id IS NULL "
                "OR s.legal_name_claim_id=$cid"
            ) in query
            if not guarded or entity["legal_name_claim_id"] in {None, params["cid"]}:
                entity["legal_name"] = params["v"]
                entity["legal_name_claim_id"] = params["cid"]
        if "SET c.status='committed'" in query:
            records[params["id"]]["status"] = "committed"
            reviews.append(params["id"])
        return []

    monkeypatch.setattr(claims.db, "transactional_write", _transaction_runner(handle))

    assert await claims.commit("claim-a") == "committed"
    assert await claims.commit("claim-b") == "committed"
    assert await claims.commit("claim-a") == "committed"
    assert await claims.commit("claim-a", refresh_materialization=True) == "committed"
    assert entity == {"legal_name": "New name", "legal_name_claim_id": "claim-b"}
    assert reviews == ["claim-a", "claim-b"]
