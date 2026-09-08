"""Truthful, bounded readiness contract for operators and judged workflows."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, db, fetch_cache
from .config import settings
from .connectors import REGISTRY
from .connectors.registry import capability_kind

_cache: dict[str, tuple[float, dict]] = {}


def invalidate_cache() -> None:
    """Drop process-local probe results when an app lifespan starts."""
    _cache.clear()
_FIXTURES = Path(__file__).resolve().parent / "seed" / "fixtures"


async def _optional_status(user: str) -> list[dict]:
    async def one(conn):
        try:
            status = await asyncio.wait_for(conn.status(user), timeout=settings.readiness_timeout_s)
            available = bool(status.get("connected"))
            needs_key = bool(status.get("needs_key"))
            return {"name": conn.name, "kind": capability_kind(conn.name), "required": False,
                    "status": "connected" if available else ("credential-required" if needs_key else "unavailable"),
                    "connected": available, "queried": True,
                    "reason": status.get("detail") or ("credential is required" if needs_key else None),
                    "action": None if available else ("add credential" if needs_key else "retry connection")}
        except Exception:
            return {"name": conn.name, "kind": capability_kind(conn.name), "required": False,
                    "status": "unavailable", "connected": False, "queried": True,
                    "reason": "connector status probe failed", "action": "retry connection"}
    return await asyncio.gather(*(one(c) for c in REGISTRY))


async def build_readiness(user: str = "local", *, refresh: bool = False) -> dict:
    now = time.time()
    cached = _cache.get(user)
    if not refresh and cached and now - cached[0] < settings.readiness_cache_s:
        return {**cached[1], "cached": True}

    database, optional = await asyncio.gather(db.probe(settings.readiness_timeout_s), _optional_status(user))
    counts = database.get("counts", {"nodes": 0, "relationships": 0})
    graph_available = database.get("reachable", False) and counts["nodes"] > 0
    seed_version = database.get("seed_version")
    actual_coverage = (
        await db.seed_coverage(database["seed_root_id"], settings.readiness_timeout_s)
        if database.get("reachable") and database.get("seed_root_id")
        else {"status": "unavailable", "root_exists": False, "primes": 0, "subs": 0}
    )
    seed_complete = (
        bool(seed_version)
        and bool(database.get("seed_completed_at"))
        and
        database.get("seed_status") == "complete"
        and actual_coverage["status"] == "validated"
        and actual_coverage["root_exists"]
        and actual_coverage["primes"] > 0
        and actual_coverage["subs"] > 0
    )
    sources: list[dict] = []
    freshness = {"status": "empty", "latest_retrieved_at": None, "age_hours": None}
    operational_live_ready = False
    operational_coverage = {"supplier_paths": 0, "live_supplier_paths": 0, "latest_retrieved_at": None}
    if database.get("reachable"):
        try:
            rows = await asyncio.wait_for(db.read(
                "CALL () { "
                " MATCH (n) WHERE n.source IS NOT NULL AND NOT n:SourceRecord "
                " AND coalesce(n.retrieval_mode, '') = 'operational_live' "
                " AND coalesce(n.latest_retrieval_status, n.retrieval_status, n.source_status, '') <> 'error' "
                " RETURN n.source AS source, count(n) AS nodes, 0 AS relationships, "
                " max(CASE WHEN coalesce(n.latest_retrieval_status, n.retrieval_status, n.source_status, '') IN ['live', 'retrieved'] THEN coalesce(n.latest_retrieved_at, n.retrieved_at, '') ELSE '' END) AS live_latest, "
                " sum(CASE WHEN coalesce(n.latest_retrieval_status, n.retrieval_status, n.source_status, '') IN ['cached', 'stale_fallback'] THEN 1 ELSE 0 END) AS cached_records, "
                " sum(CASE WHEN coalesce(n.latest_retrieval_status, n.retrieval_status, n.source_status, '') NOT IN ['live', 'retrieved', 'cached', 'stale_fallback'] THEN 1 ELSE 0 END) AS unknown_records "
                " UNION ALL "
                " MATCH ()-[r]->() WHERE r.source IS NOT NULL "
                " AND coalesce(r.retrieval_mode, '') = 'operational_live' "
                " AND coalesce(r.latest_retrieval_status, r.retrieval_status, r.source_status, '') <> 'error' "
                " RETURN r.source AS source, 0 AS nodes, count(r) AS relationships, "
                " max(CASE WHEN coalesce(r.latest_retrieval_status, r.retrieval_status, r.source_status, '') IN ['live', 'retrieved'] THEN coalesce(r.latest_retrieved_at, r.retrieved_at, '') ELSE '' END) AS live_latest, "
                " sum(CASE WHEN coalesce(r.latest_retrieval_status, r.retrieval_status, r.source_status, '') IN ['cached', 'stale_fallback'] THEN 1 ELSE 0 END) AS cached_records, "
                " sum(CASE WHEN coalesce(r.latest_retrieval_status, r.retrieval_status, r.source_status, '') NOT IN ['live', 'retrieved', 'cached', 'stale_fallback'] THEN 1 ELSE 0 END) AS unknown_records "
                "} RETURN source, sum(nodes) AS nodes, sum(relationships) AS relationships, "
                "max(live_latest) AS latest, sum(cached_records) AS cached_records, sum(unknown_records) AS unknown_records "
                "ORDER BY nodes + relationships DESC", timeout=settings.readiness_timeout_s),
                timeout=settings.readiness_timeout_s + .25)
            procurement_rows = await asyncio.wait_for(
                db.read(
                    "MATCH (s:Entity)-[r:SUPPLIES]->(p:Entity) "
                    "WHERE s.kind='organization' AND p.kind='program' "
                    "AND coalesce(s.simulated,false)=false AND coalesce(p.simulated,false)=false "
                    "AND coalesce(r.simulated,false)=false "
                    "AND toLower(coalesce(r.source,'')) IN ['usaspending','usaspending.gov'] "
                    "AND coalesce(r.retrieval_mode,'')='operational_live' "
                    "WITH r, coalesce(r.latest_retrieval_status,r.retrieval_status,r.source_status,'') AS status "
                    "RETURN count(r) AS records, "
                    "sum(CASE WHEN status IN ['live','retrieved'] THEN 1 ELSE 0 END) AS live_records, "
                    "max(CASE WHEN status IN ['live','retrieved'] "
                    "THEN coalesce(r.latest_retrieved_at,r.retrieved_at,'') ELSE '' END) AS latest",
                    timeout=settings.readiness_timeout_s,
                ),
                timeout=settings.readiness_timeout_s + .25,
            )
            by_source = {r["source"]: r for r in rows}
            optional_by_name = {item["name"]: item for item in optional}
            source_names = list(dict.fromkeys([*(c.name for c in REGISTRY), *by_source]))
            sources = []
            for source in source_names:
                r = by_source.get(source)
                service = optional_by_name.get(source, {})
                # `latest` is deliberately live-only. A cache file's ingestion
                # time is not evidence that the remote source was just queried.
                latest_source = r.get("latest") if r else None
                cached_records = int(r.get("cached_records", 0) or 0) if r else 0
                unknown_records = int(r.get("unknown_records", 0) or 0) if r else 0
                source_age = None
                if latest_source:
                    try:
                        observed = datetime.fromisoformat(str(latest_source).replace("Z", "+00:00"))
                        source_age = round((datetime.now(timezone.utc) - observed).total_seconds() / 3600, 1)
                    except (TypeError, ValueError):
                        pass
                if r and source_age is not None and source_age > settings.freshness_stale_hours:
                    source_status = "stale-fallback"
                elif r and cached_records:
                    source_status = "stale-fallback"
                elif r and unknown_records:
                    source_status = "unknown"
                elif r:
                    source_status = "current"
                else:
                    source_status = service.get("status", "unavailable")
                sources.append({
                    "source": source, "nodes": r["nodes"] if r else 0,
                    "relationships": r["relationships"] if r else 0,
                    "records": (r["nodes"] + r["relationships"]) if r else 0,
                    "queried": bool(r), "applicable": None,
                    "reason": None if r else service.get("reason") or "no successful retrieval is recorded",
                    "status": source_status, "last_success_at": latest_source or None,
                    "latest_retrieved_at": latest_source or None,
                    "cache": bool(cached_records), "unknown_records": unknown_records,
                    "simulated": source == "scenario",
                    "action": "refresh source" if source_status == "stale-fallback" else service.get("action"),
                })
            latest = max((r.get("latest") for r in rows if r.get("latest")), default=None)
            procurement = procurement_rows[0] if procurement_rows else {}
            operational_coverage = {
                "supplier_paths": int(procurement.get("records", 0) or 0),
                "live_supplier_paths": int(procurement.get("live_records", 0) or 0),
                "latest_retrieved_at": procurement.get("latest") or None,
            }
            procurement_latest = operational_coverage["latest_retrieved_at"]
            if operational_coverage["live_supplier_paths"] and procurement_latest:
                try:
                    procurement_observed = datetime.fromisoformat(
                        str(procurement_latest).replace("Z", "+00:00")
                    )
                    operational_live_ready = (
                        datetime.now(timezone.utc) - procurement_observed
                    ).total_seconds() / 3600 <= settings.freshness_stale_hours
                except (TypeError, ValueError):
                    operational_live_ready = False
            age_hours = None
            if latest:
                try:
                    observed = datetime.fromisoformat(str(latest).replace("Z", "+00:00"))
                    age_hours = round((datetime.now(timezone.utc) - observed).total_seconds() / 3600, 1)
                except (TypeError, ValueError):
                    pass
            freshness = {
                "status": "stale" if age_hours is not None and age_hours > settings.freshness_stale_hours else ("current" if latest else "unknown"),
                "latest_retrieved_at": latest,
                "age_hours": age_hours,
                "action": "refresh source data when optional services are available" if age_hours is not None and age_hours > settings.freshness_stale_hours else None,
            }
        except Exception:
            freshness = {"status": "unknown", "latest_retrieved_at": None, "age_hours": None, "action": "retry readiness probe"}

    required = {
        "api": {"status": "ready", "version": __version__},
        "neo4j": database,
        "seed": {"status": "ready" if seed_complete else ("incomplete" if seed_version else ("unknown" if graph_available else "empty")),
                 "version": seed_version or ("legacy-unversioned" if graph_available else None),
                 "completed_at": database.get("seed_completed_at"),
                 "root_id": database.get("seed_root_id"),
                 "offline": bool(database.get("seed_offline")),
                 "scenario": bool(database.get("seed_scenario")),
                 "coverage": {"status": actual_coverage["status"], "root_exists": actual_coverage["root_exists"],
                              "primes": actual_coverage["primes"], "subcontractors": actual_coverage["subs"]},
                 "fixture_files": sum(1 for p in _FIXTURES.iterdir() if p.is_file()) if _FIXTURES.exists() else 0,
                 "action": None if seed_complete else "run illuminate-seed --offline to build and stamp the deterministic dataset"},
    }
    cache_ready = (
        not settings.illuminate_fetch_cache_authority_enabled
        or fetch_cache.schema_ready()
    )
    if settings.illuminate_fetch_cache_authority_enabled:
        required["fetch_cache"] = {
            "status": "ready" if cache_ready else "unavailable",
            "namespace": settings.illuminate_fetch_cache_namespace,
            "immutable": True,
        }
    primary_ready = bool(database.get("reachable") and seed_complete)
    if not database.get("reachable"):
        status = "unavailable"
    elif not primary_ready or freshness["status"] in ("stale", "unknown", "empty"):
        status = "degraded"
    else:
        status = "ready"
    startup_ready = bool(database.get("reachable") and cache_ready)
    result = {"ok": startup_ready, "version": __version__, "status": status,
              "primary_workflow_ready": primary_ready, "neo4j": startup_ready, "required": required,
              "operational_live_ready": operational_live_ready,
              "operational_refresh_required": bool(startup_ready and not operational_live_ready),
              "operational_coverage": operational_coverage,
              "graph_counts": counts, "source_coverage": sources, "freshness": freshness,
              "optional_services": optional,
              "message": "Database is ready; live source refresh may continue in the background." if startup_ready
                         else "Database is unavailable; retry after database recovery.", "cached": False}
    if len(_cache) >= 100 and user not in _cache:
        _cache.clear()
    _cache[user] = (now, result)
    return result