from types import SimpleNamespace
from unittest.mock import AsyncMock

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
    assert len(metadata_writes) == 1
    metadata = metadata_writes[0]
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