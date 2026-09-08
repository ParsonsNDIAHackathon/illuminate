from types import SimpleNamespace
from unittest.mock import AsyncMock

from illuminate.connectors.base import ArtifactRef, Fact, NodeRef
from illuminate.enrichment import claims
from illuminate.seed import seed


async def test_seed_orchestration_runs_scenario_and_stamps_program_identity(monkeypatch):
    root = {"root_id": "ent_program", "root_name": "Program", "primes": 2, "subs": 3}
    metadata_writes = []

    monkeypatch.setattr(seed, "ensure_schema", AsyncMock())
    monkeypatch.setattr(seed, "seed_catalog_lineage", AsyncMock())
    monkeypatch.setattr(seed, "seed_program", AsyncMock(return_value=root))
    monkeypatch.setattr(seed, "seed_cached_gdelt", AsyncMock())
    monkeypatch.setattr(seed, "scenario", AsyncMock())
    monkeypatch.setattr(seed, "stats", AsyncMock(return_value={"nodes": {}, "rels": {}}))
    monkeypatch.setattr(seed.db, "read", AsyncMock(return_value=[]))
    monkeypatch.setattr(seed.db, "close_driver", AsyncMock())

    async def capture_write(statement, params=None):
        if "SeedMetadata" in statement:
            metadata_writes.append(params)
        return {"rows": [], "counters": {}}

    monkeypatch.setattr(seed.db, "write", capture_write)
    args = SimpleNamespace(
        offline=True,
        reset=False,
        keyword=["program"],
        root_name="Program",
        since="2024-01-01",
        until="2026-01-01",
        primes=2,
        subs=3,
        agency="Agency",
        people=0,
        skip_enrich=True,
        scenario=True,
    )

    await seed.main_async(args)

    seed.scenario.assert_awaited_once_with("ent_program")
    assert len(metadata_writes) == 2
    started, metadata = metadata_writes
    assert started.pop("started")
    assert started == {
        "version": seed.SEED_VERSION,
        "offline": True,
        "scenario": True,
    }
    assert metadata.pop("completed")
    assert metadata == {
        "version": seed.SEED_VERSION,
        "offline": True,
        "scenario": True,
        "root_id": "ent_program",
        "status": "complete",
        "primes": 2,
        "subs": 3,
    }


async def test_interrupted_reset_invalidates_prior_completion_before_deleting_data(monkeypatch):
    writes = []

    monkeypatch.setattr(seed, "ensure_schema", AsyncMock())
    monkeypatch.setattr(seed, "seed_catalog_lineage", AsyncMock())
    monkeypatch.setattr(
        seed,
        "seed_program",
        AsyncMock(side_effect=RuntimeError("simulated interruption")),
    )
    monkeypatch.setattr(seed.db, "close_driver", AsyncMock())

    async def capture_write(statement, params=None):
        writes.append((statement, params))
        return {"rows": [], "counters": {}}

    monkeypatch.setattr(seed.db, "write", capture_write)
    args = SimpleNamespace(
        offline=True,
        reset=True,
        keyword=["program"],
        root_name="Program",
        since="2024-01-01",
        until="2026-01-01",
        primes=2,
        subs=3,
        agency="Agency",
        people=0,
        skip_enrich=True,
        scenario=True,
    )

    with __import__("pytest").raises(RuntimeError, match="simulated interruption"):
        await seed.main_async(args)

    assert "status='running'" in writes[0][0]
    assert "DETACH DELETE" in writes[1][0]
    assert not any("status=$status" in statement for statement, _ in writes)


def test_seed_claim_identity_is_stable_and_distinguishes_evidence():
    fact = Fact(
        subject=NodeRef("Entity", "ent_1"),
        predicate="sanctions_screen",
        value="clear",
        artifact=ArtifactRef(
            url="https://example.test/record/1",
            title="Record title can be refreshed",
            published_at="2026-09-08",
        ),
    )
    same_observation = Fact(
        subject=NodeRef("Entity", "ent_1"),
        predicate="sanctions_screen",
        value="clear",
        artifact=ArtifactRef(
            url="https://example.test/record/1",
            title="Updated display title",
            published_at="2026-09-08",
        ),
    )
    other_evidence = Fact(
        subject=NodeRef("Entity", "ent_1"),
        predicate="sanctions_screen",
        value="clear",
        artifact=ArtifactRef(
            url="https://example.test/record/2",
            title="Other record",
            published_at="2026-09-08",
        ),
    )

    first = claims.observation_key(fact, "ofac")
    assert first == claims.observation_key(same_observation, "ofac")
    assert first != claims.observation_key(other_evidence, "ofac")
    assert first.startswith("clm_obs_")


async def test_replayed_committed_observation_uses_idempotent_refresh(monkeypatch):
    monkeypatch.setattr(
        claims.db,
        "read",
        AsyncMock(return_value=[{"c": {
            "id": "clm_seed_1",
            "status": "committed",
            "predicate": "sanctions_screen",
            "confidence": 1.0,
        }}]),
    )
    commit = AsyncMock(return_value="committed")
    monkeypatch.setattr(claims, "commit", commit)

    assert await claims.decide("clm_seed_1", trust="authoritative") == "committed"
    commit.assert_awaited_once_with("clm_seed_1")