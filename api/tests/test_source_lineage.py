import json
import asyncio
import time
from pathlib import Path

from illuminate.connectors.registry import SOURCE_METADATA, get_connector, source_metadata
from illuminate.connectors.http import HttpError
from illuminate.connectors.base import Fact, NodeRef
from illuminate.enrichment import claims


def test_named_judged_sources_have_normalized_metadata():
    for name in ("usaspending", "gdelt", "opencorporates", "gleif", "edgar", "littlesis", "ofac", "sam_exclusions"):
        meta = source_metadata(name)
        assert meta["source_id"]
        assert meta["usage_note"]
        assert meta["quality_note"]
        assert meta["supports"]
        assert meta["unknowns"]


def test_catalog_fixture_covers_primary_judged_datasets():
    path = Path(__file__).parents[1] / "illuminate" / "seed" / "fixtures" / "catalog_lineage.json"
    records = json.loads(path.read_text())["records"]
    by_catalog = {catalog_id: record for record in records for catalog_id in record["catalog_ids"]}
    assert set(by_catalog) == {"ndia:1", "ndia:49", "ndia:62"}
    for record in records:
        assert record["retrieved_at"]
        assert record["source_identifier"]
        assert record["source_url"]
        assert (path.parent / record["cache_fixture"]).exists()
        assert record["source_status"] == "cached"
        assert record["simulated"] is False
        cached = json.loads((path.parent / record["cache_fixture"]).read_text())
        stamp = cached.get("_ts") or cached.get("retrieved_at")
        expected = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stamp)) if isinstance(stamp, (int, float)) else stamp
        assert record["retrieved_at"] == expected
    assert by_catalog["ndia:1"]["connector"] == "usaspending"
    assert by_catalog["ndia:49"]["connector"] == "sam"
    assert by_catalog["ndia:62"]["connector"] == "gdelt"
    assert by_catalog["ndia:62"]["cache_fixture"] != path.name
    gdelt = json.loads((path.parent / by_catalog["ndia:62"]["cache_fixture"]).read_text())
    assert gdelt["gkg_record_id"] == by_catalog["ndia:62"]["source_identifier"]
    assert gdelt["article_url"].startswith("https://")
    assert gdelt["bulk_md5"]


def test_source_metadata_returns_a_copy():
    first = source_metadata("usaspending")
    first["catalog_ids"].append("changed")
    assert "changed" not in SOURCE_METADATA["usaspending"]["catalog_ids"]


def test_connector_api_exposes_coverage_and_limits():
    data = get_connector("gdelt").to_dict()
    assert data["source_id"] == "gdelt-2.x"
    assert data["catalog_ids"] == ["ndia:62"]
    assert data["supports"]
    assert data["unknowns"]
    assert get_connector("sam").to_dict()["catalog_ids"] == ["ndia:49"]
    assert get_connector("usaspending").to_dict()["catalog_ids"] == ["ndia:1"]


def test_rejected_claim_cannot_be_committed():
    original_read = claims.db.read
    original_write = claims.db.write
    writes = []

    async def fake_read(query, params=None):
        if "ASSERTS" in query:
            return [{"c": {"status": "rejected"}, "sid": "ent_1", "oid": None}]
        return []

    async def fake_write(query, params=None):
        writes.append((query, params))

    async def check():
        claims.db.read = fake_read
        claims.db.write = fake_write
        try:
            assert await claims.commit("clm_rejected") == "rejected"
            assert writes == []
        finally:
            claims.db.read = original_read
            claims.db.write = original_write

    asyncio.run(check())


def test_report_queries_require_committed_screens():
    report = (Path(__file__).parents[1] / "illuminate" / "report.py").read_text()
    assert '"screens": [] if e.get("simulated") else [' in report
    assert 's for s in scr if s.get("status") == "committed" and not _screen_simulated(s)' in report
    assert '"screen_evidence": scr' in report

def test_connector_errors_never_persist_exception_messages():
    secret = "synthetic-secret-must-not-survive"
    error = HttpError(403, f"https://example.test/path?api_token={secret}", f"body {secret}")
    safe = claims.connector_error_metadata(error)
    assert safe == {
        "connector_error": "HttpError (HTTP 403)",
        "connector_error_type": "HttpError",
        "connector_error_status": 403,
    }
    assert secret not in json.dumps(safe)

    original_write = claims.db.write
    captured = {}

    async def fake_write(query, params=None):
        captured.update(params)

    async def check():
        claims.db.write = fake_write
        try:
            await claims.record_connector_error("opencorporates", "ent_1", error)
        finally:
            claims.db.write = original_write

    asyncio.run(check())
    assert secret not in json.dumps(captured)

    generic = claims.connector_error_metadata(RuntimeError(f"failed with api_key={secret}"))
    assert generic["connector_error"] == "RuntimeError"
    assert secret not in json.dumps(generic)

def test_artifact_list_preserves_claim_count_contract():
    graph_router = (Path(__file__).parents[1] / "illuminate" / "routers" / "graph.py").read_text()
    assert "count(DISTINCT c) AS claims" in graph_router
    assert "collect(DISTINCT c.status) AS claim_statuses" in graph_router
    assert "a.source_identifier AS source_identifier" in graph_router


def test_versioned_export_preserves_claim_and_evidence_lineage():
    from illuminate.routers import exports

    row = {
        "claim_id": "clm_lineage", "subject_id": "ent_1", "subject_type": "Entity",
        "subject_name": "Supplier", "predicate": "adverse_media_screen", "status": "committed",
        "source": "gdelt", "source_id": "gdelt-2.x", "source_identifier": "claim-record",
        "catalog_ids": ["ndia:62"], "source_url": "https://example.test/claim",
        "retrieved_at": "2026-09-08T16:00:00Z", "usage_note": "public metadata",
        "quality_note": "automated lead", "supports": "media discovery",
        "unknowns": "does not establish fault", "source_status": "committed",
        "claim_simulated": False, "subject_simulated": False, "targets": [],
        "artifacts": [{
            "id": "art_1", "title": "Cached article", "source": "GDELT",
            "source_id": "gdelt-2.x", "source_identifier": "20260908160000-92",
            "catalog_ids": ["ndia:62"], "source_url": "https://example.test/article",
            "retrieved_at": "2026-09-08T16:00:00Z", "source_status": "cached",
            "simulated": False, "evidence_present": True, "evidence_source": "gdelt",
            "evidence_source_id": "gdelt-2.x", "evidence_catalog_ids": ["ndia:62"],
            "evidence_retrieved_at": "2026-09-08T16:00:00Z",
            "evidence_usage_note": "public metadata", "evidence_quality_note": "automated lead",
            "evidence_supports": "media discovery", "evidence_unknowns": "does not establish fault",
            "evidence_source_status": "retrieved", "evidence_simulated": True,
        }],
        "observed": "2026-09-08T16:00:00Z",
    }
    finding = exports._finding(row)
    fields = exports.Provenance.model_json_schema()["properties"]
    assert {"source_id", "source_identifier", "catalog_ids", "usage_note", "quality_note",
            "supports", "unknowns", "source_status", "connector_error_type", "simulated"} <= set(fields)
    by_scope = {item.scope: item for item in finding.provenance}
    assert by_scope["claim"].catalog_ids == ["ndia:62"]
    assert by_scope["artifact"].source_identifier == "20260908160000-92"
    assert by_scope["artifact"].source_status == "cached"
    assert by_scope["evidence"].source_id == "gdelt-2.x"
    assert by_scope["evidence"].quality_note == "automated lead"
    assert by_scope["evidence"].simulated is True
    assert finding.simulated is True
    before = finding.model_dump_json()
    row["artifacts"][0]["evidence_catalog_ids"] = ["ndia:62", "ndia:future"]
    assert exports._finding(row).model_dump_json() != before

def test_worker_diagnostics_use_safe_error_metadata():
    worker = (Path(__file__).parents[1] / "illuminate" / "enrichment" / "worker.py").read_text()
    assert worker.count("claims.connector_error_metadata") >= 2
    assert "str(e)" not in worker
    assert "str(error)" not in worker

def test_relationship_simulation_survives_stage_and_commit():
    original_read = claims.db.read
    original_write = claims.db.write
    stage_writes = []
    commit_writes = []

    async def stage_read(query, params=None):
        if "RETURN e.id AS id" in query:
            return [{"id": params["id"]}]
        return []

    async def stage_write(query, params=None):
        stage_writes.append((query, params))

    async def check():
        claims.db.read = stage_read
        claims.db.write = stage_write
        try:
            fact = Fact(
                NodeRef("Entity", "ent_real_1"),
                "SUPPLIES",
                object=NodeRef("Entity", "ent_real_2"),
                props={"tier": 2, "simulated": True},
            )
            await claims.stage(fact, source="usaspending", trust="authoritative")
            staged = stage_writes[-1][1]
            assert staged["simulated"] is True
            assert json.loads(staged["rel_props_json"])["simulated"] is True

            async def commit_read(query, params=None):
                if "RETURN c{.*} AS c" in query:
                    return [{
                        "c": {
                            "status": "staged", "predicate": "SUPPLIES", "source": "usaspending",
                            "retrieved_at": "2026-09-08T00:00:00Z", "method": "connector",
                            "confidence": 1.0, "simulated": False,
                            "rel_props": json.dumps({"tier": 2, "simulated": True}),
                        },
                        "sid": "ent_real_1", "oid": "ent_real_2",
                    }]
                return []

            async def commit_write(query, params=None):
                commit_writes.append((query, params))

            claims.db.read = commit_read
            claims.db.write = commit_write
            assert await claims.commit("clm_sim") == "committed"
            relationship = next(params for query, params in commit_writes if "MERGE (s)-[r:SUPPLIES" in query)
            assert relationship["rp"]["simulated"] is True
            assert relationship["prov"]["simulated"] is True
        finally:
            claims.db.read = original_read
            claims.db.write = original_write

    asyncio.run(check())

def test_shared_artifact_lineage_is_not_rewritten():
    source = (Path(__file__).parents[1] / "illuminate" / "enrichment" / "claims.py").read_text()
    artifact_clause = source.split('"MERGE (a:Artifact {id:$aid})', 1)[1].split('"MERGE (a)-[re:EVIDENCES]', 1)[0]
    assert "ON CREATE SET" in artifact_clause
    assert '"SET a +=' not in artifact_clause
    evidence_clause = source.split('"MERGE (a)-[re:EVIDENCES]', 1)[1].split('"MERGE (a)-[rb:ABOUT]', 1)[0]
    assert "re.source=$source" in evidence_clause
    assert "re.simulated=$simulated" in evidence_clause
    assert "re += $source_meta" in evidence_clause

def test_seed_ingests_cached_gdelt_evidence():
    seed = (Path(__file__).parents[1] / "illuminate" / "seed" / "seed.py").read_text()
    assert 'CATALOG_FIXTURE = FIXTURES / "catalog_lineage.json"' in seed
    assert 'async def seed_cached_gdelt() -> bool' in seed
    assert "association skipped" in seed
    assert 'await seed_cached_gdelt()' in seed


def test_seed_catalog_lineage_executes_fixture_writes():
    from illuminate.seed import seed as seed_module

    original_write = seed_module.db.write
    writes = []

    async def fake_write(query, params=None):
        writes.append((query, params))

    async def check():
        seed_module.db.write = fake_write
        try:
            await seed_module.seed_catalog_lineage()
        finally:
            seed_module.db.write = original_write

    asyncio.run(check())
    assert len(writes) == 3
    assert {params["id"] for _, params in writes} == {
        "src_ndia_1_federal_spending",
        "src_ndia_49_contract_award",
        "src_ndia_62_gdelt",
    }
    for query, params in writes:
        assert "ON CREATE SET r += $meta, r += $record" in query
        assert "SET r.last_ingested_at=$ingested" in query
        assert params["record"]["retrieved_at"]


def test_seed_catalog_reuse_preserves_original_retrieval():
    from illuminate.seed import seed as seed_module

    original_write = seed_module.db.write
    stored = {}

    async def fake_write(query, params=None):
        current = stored.get(params["id"])
        if current is None:
            current = {**params["meta"], **params["record"], "first_ingested_at": params["ingested"]}
            stored[params["id"]] = current
        elif "ON CREATE SET r += $meta, r += $record" not in query:
            current.update(params["meta"])
            current.update(params["record"])
        current["last_ingested_at"] = params["ingested"]

    async def check():
        seed_module.db.write = fake_write
        try:
            await seed_module.seed_catalog_lineage()
            stored["src_ndia_62_gdelt"]["retrieved_at"] = "2026-08-31T12:00:00Z"
            stored["src_ndia_62_gdelt"]["source_identifier"] = "original-cache-record"
            await seed_module.seed_catalog_lineage()
        finally:
            seed_module.db.write = original_write

    asyncio.run(check())
    gdelt = stored["src_ndia_62_gdelt"]
    assert gdelt["retrieved_at"] == "2026-08-31T12:00:00Z"
    assert gdelt["source_identifier"] == "original-cache-record"
    assert gdelt["last_ingested_at"]


def test_seed_artifact_reuse_preserves_original_provenance():
    from illuminate.seed import seed as seed_module

    original_write = seed_module.db.write
    stored = {}

    async def fake_write(query, params=None):
        if "MERGE (a:Artifact" not in query:
            return
        current = stored.get(params["id"])
        if current is None:
            current = dict(params["p"])
            current["first_ingested_at"] = params["ingested"]
            stored[params["id"]] = current
        elif "ON CREATE SET a += $p" not in query:
            current.update(params["p"])
        current["last_ingested_at"] = params["ingested"]

    async def check():
        seed_module.db.write = fake_write
        try:
            await seed_module.merge_artifact(
                "art_shared",
                {"source": "USAspending", "url": "https://example.test/shared", "retrieved_at": "2026-09-01T00:00:00Z", "simulated": True},
                "ent_one",
            )
            await seed_module.merge_artifact(
                "art_shared",
                {"source": "GDELT", "url": "https://example.test/shared", "retrieved_at": "2026-09-08T00:00:00Z", "simulated": False},
                "ent_two",
            )
        finally:
            seed_module.db.write = original_write

    asyncio.run(check())
    artifact = stored["art_shared"]
    assert artifact["source"] == "USAspending"
    assert artifact["retrieved_at"] == "2026-09-01T00:00:00Z"
    assert artifact["simulated"] is True
    assert artifact["last_ingested_at"]

def test_cached_gdelt_never_falls_back_to_an_unrelated_root():
    from illuminate.seed import seed as seed_module

    original_read = seed_module.db.read
    original_merge = seed_module.merge_artifact
    merges = []

    async def no_match(query, params=None):
        return []

    async def fake_merge(*args, **kwargs):
        merges.append((args, kwargs))

    async def check():
        seed_module.db.read = no_match
        seed_module.merge_artifact = fake_merge
        try:
            assert await seed_module.seed_cached_gdelt() is False
            assert merges == []

            async def matched(query, params=None):
                return [{"id": "ent_boeing"}]

            seed_module.db.read = matched
            assert await seed_module.seed_cached_gdelt() is True
            assert await seed_module.seed_cached_gdelt() is True
            props = merges[0][0][1]
            fixture = json.loads((Path(seed_module.__file__).parent / "fixtures" / "gdelt_gkg_20260908160000_92.json").read_text())
            assert props["retrieved_at"] == fixture["retrieved_at"]
            assert props["source_status"] == "cached"
            assert merges[0][0][2] == "ent_boeing"
            assert merges[1][0][1]["retrieved_at"] == fixture["retrieved_at"]
            assert merges[1][0][2] == "ent_boeing"
        finally:
            seed_module.db.read = original_read
            seed_module.merge_artifact = original_merge

    asyncio.run(check())
