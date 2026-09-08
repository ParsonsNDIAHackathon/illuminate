"""Truthful, bounded readiness contract for operators and judged workflows."""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

from . import __version__, db
from .config import settings
from .connectors import REGISTRY
from .connectors.registry import capability_kind

_cache: dict[str, tuple[float, dict]] = {}
_FIXTURES = Path(__file__).resolve().parent / "seed" / "fixtures"


async def _optional_status(user: str) -> list[dict]:
    async def one(conn):
        try:
            status = await asyncio.wait_for(conn.status(user), timeout=settings.readiness_timeout_s)
            available = bool(status.get("connected"))
            return {"name": conn.name, "kind": capability_kind(conn.name), "required": False,
                    "status": "available" if available else "unavailable",
                    "action": None if available else ("configure credential to enable" if status.get("needs_key") else "retry later")}
        except Exception:
            return {"name": conn.name, "kind": capability_kind(conn.name), "required": False,
                    "status": "unavailable", "action": "retry later"}
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
    if database.get("reachable"):
        try:
            rows = await asyncio.wait_for(db.read(
                "CALL () { "
                " MATCH (n) WHERE n.source IS NOT NULL "
                " RETURN n.source AS source, count(n) AS nodes, 0 AS relationships, max(coalesce(n.retrieved_at, '')) AS latest "
                " UNION ALL "
                " MATCH ()-[r]->() WHERE r.source IS NOT NULL "
                " RETURN r.source AS source, 0 AS nodes, count(r) AS relationships, max(coalesce(r.retrieved_at, '')) AS latest "
                "} RETURN source, sum(nodes) AS nodes, sum(relationships) AS relationships, max(latest) AS latest "
                "ORDER BY nodes + relationships DESC", timeout=settings.readiness_timeout_s),
                timeout=settings.readiness_timeout_s + .25)
            sources = [{"source": r["source"], "nodes": r["nodes"], "relationships": r["relationships"],
                        "records": r["nodes"] + r["relationships"], "latest_retrieved_at": r.get("latest") or None} for r in rows]
            latest = max((r.get("latest") for r in rows if r.get("latest")), default=None)
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
                 "coverage": {"status": actual_coverage["status"], "root_exists": actual_coverage["root_exists"],
                              "primes": actual_coverage["primes"], "subcontractors": actual_coverage["subs"]},
                 "fixture_files": sum(1 for p in _FIXTURES.iterdir() if p.is_file()) if _FIXTURES.exists() else 0,
                 "action": None if seed_complete else "run illuminate-seed --offline to build and stamp the deterministic dataset"},
    }
    primary_ready = bool(database.get("reachable") and seed_complete)
    if not database.get("reachable"):
        status = "unavailable"
    elif not primary_ready or freshness["status"] in ("stale", "unknown", "empty"):
        status = "degraded"
    else:
        status = "ready"
    startup_ready = bool(database.get("reachable"))
    result = {"ok": startup_ready, "version": __version__, "status": status,
              "primary_workflow_ready": primary_ready, "neo4j": startup_ready, "required": required,
              "graph_counts": counts, "source_coverage": sources, "freshness": freshness,
              "optional_services": optional,
              "message": "Deterministic workflow is ready; optional services may be unavailable." if primary_ready
                         else "Primary workflow needs operator action.", "cached": False}
    if len(_cache) >= 100 and user not in _cache:
        _cache.clear()
    _cache[user] = (now, result)
    return result