"""Background enrichment. Runs unattended against connectors, so it needs a rule
rather than a prompt: it proposes claims and the trust rule in claims.py commits."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .. import db, events
from ..config import settings
from ..connectors import REGISTRY, get_connector
from ..connectors.http import RetrievalMode, retrieval_context
from ..connectors.validation import validate_facts
from . import claims
from . import checkpoints
from .sources import select_connectors

Listener = Callable[[str, dict], Awaitable[None]]


@dataclass
class Job:
    id: str
    entity_id: str
    entity_name: str | None
    connectors: list[str]
    user: str = "local"
    requested_by: str = "ui"
    retrieval_mode: RetrievalMode = "operational_live"
    resumed_from: str | None = None
    parent_job_id: str | None = None
    selection: dict = field(default_factory=dict)
    status: str = "queued"           # queued | running | succeeded | empty | partial | failed | timed_out
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    results: dict = field(default_factory=dict)   # connector -> {facts, staged, committed, error}
    summary_updated: bool = False
    summary_status: str = "not_requested"
    status_version: int = 2

    def to_dict(self) -> dict:
        out = self.__dict__.copy()
        out["terminal"] = self.status not in ("queued", "running")
        return out


class Worker:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[Job] = asyncio.Queue()
        self.jobs: dict[str, Job] = {}
        self._task: asyncio.Task | None = None
        self._listeners: set[Listener] = set()

    def add_listener(self, fn: Listener) -> None:
        self._listeners.add(fn)

    def remove_listener(self, fn: Listener) -> None:
        self._listeners.discard(fn)

    async def _emit(self, event: str, payload: dict) -> None:
        for fn in list(self._listeners):
            try:
                await fn(event, payload)
            except Exception:
                self._listeners.discard(fn)

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def recover_interrupted(self) -> int:
        """Retire stale process-owned checkpoints before accepting new work."""
        try:
            return await checkpoints.interrupt_active()
        except Exception:
            return 0

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def enqueue(self, entity_id: str, connectors: list[str] | None = None, user: str = "local",
                      requested_by: str = "ui", retrieval_mode: RetrievalMode = "operational_live",
                       resume_job_id: str | None = None, parent_job_id: str | None = None) -> Job:
        rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": entity_id})
        entity = rows[0]["e"] if rows else {}
        previous = self.jobs.get(resume_job_id) if resume_job_id else None
        stored = await checkpoints.load(resume_job_id) if resume_job_id and previous is None else None
        if resume_job_id and previous is None and stored is None:
            raise ValueError("resume job was not found")
        previous_entity = previous.entity_id if previous else (stored or {}).get("entity_id")
        if previous_entity and previous_entity != entity_id:
            raise ValueError("resume job belongs to a different entity")
        previous_connectors = previous.connectors if previous else (stored or {}).get("connectors")
        previous_results = previous.results if previous else (stored or {}).get("results")
        requested = connectors if connectors is not None else previous_connectors
        names = select_connectors(entity, REGISTRY, requested=requested,
                                  previous_results=previous_results)
        selection = {
            c.name: {"status": "not_applicable", "reason": f"source does not speak about a {entity.get('kind') or 'organization'}"}
            for c in REGISTRY if c.name != "openai" and not c.applies_to(entity)
        } if connectors is None else {}
        job = Job(id="job_" + uuid.uuid4().hex[:8], entity_id=entity_id, entity_name=entity.get("name"),
                  connectors=names, user=user, requested_by=requested_by, retrieval_mode=retrieval_mode,
                  resumed_from=previous.id if previous else ((stored or {}).get("id") if stored else None),
                   parent_job_id=parent_job_id, selection=selection)
        self.jobs[job.id] = job
        await self._checkpoint(job)
        if resume_job_id:
            try:
                await checkpoints.mark_superseded(resume_job_id, job.id)
            except Exception:
                job.results["_checkpoint_error"] = (
                    "resume was queued but the previous checkpoint could not be marked superseded"
                )
        await self.queue.put(job)
        self.start()
        await self._emit("job_update", job.to_dict())
        return job

    async def _loop(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                await self.run(job)
            except Exception as e:
                job.status = "failed"
                safe_error = claims.connector_error_metadata(e)["connector_error"]
                job.results["_error"] = f"{safe_error}: job failed; retry or inspect service readiness"
                job.finished_at = time.time()
                await self._emit("job_update", job.to_dict())
            finally:
                self.queue.task_done()

    async def run(self, job: Job) -> None:
        job.status = "running"
        job.started_at = time.time()
        await self._checkpoint(job)
        await self._emit("job_update", job.to_dict())
        try:
            await asyncio.wait_for(self._execute(job), timeout=settings.enrichment_job_timeout_s)
        except (asyncio.TimeoutError, TimeoutError):
            job.results["_job_error"] = "job deadline exceeded; completed connector results were preserved"
            for name in job.connectors:
                existing = job.results.get(name)
                if isinstance(existing, dict) and existing.get("status") == "running":
                    stored = existing.get("staged", 0) + existing.get("committed", 0) + existing.get("rejected", 0)
                    existing.update(
                        status="partial" if stored else "timed_out",
                        error="job deadline reached during connector processing",
                        action="retry; successfully stored facts were preserved",
                    )
                job.results.setdefault(name, {
                    "status": "not_run", "error": "job deadline reached before completion",
                    "action": "retry this enrichment job", "attempts": 0,
                })
            if job.summary_status in {"not_requested", "running"}:
                await self._clear_summary_selection(job)
                job.summary_status = "timed_out"
        except Exception as e:
            safe_error = claims.connector_error_metadata(e)["connector_error"]
            job.results["_error"] = f"{safe_error}: job failed; retry or inspect service readiness"
            if job.summary_status in {"not_requested", "running"}:
                await self._clear_summary_selection(job)
        self._set_status(job)
        job.finished_at = time.time()
        await self._checkpoint(job)
        await self._emit("job_update", job.to_dict())
        await events.announce([job.entity_id], reason="enrich:done", source="enrichment")

    async def _execute(self, job: Job) -> None:
        rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": job.entity_id})
        if not rows:
            job.results["_error"] = "entity not found"
            return
        entity = rows[0]["e"]
        for name in job.connectors:
            conn = get_connector(name)
            if not conn:
                job.results[name] = {"status": "failed", "error": "unknown connector", "action": "remove or configure this connector", "attempts": 0}
                continue
            applies_to = getattr(conn, "applies_to", None)
            if applies_to and not applies_to(entity):
                job.results[name] = {
                    "status": "skipped", "queried": False, "applicable": False,
                    "availability": "not-applicable",
                    "reason": f"source does not speak about a {entity.get('kind') or 'organization'}",
                    "error": f"source does not speak about a {entity.get('kind') or 'organization'}",
                    "action": None,
                    "attempts": 0,
                }
                await self._emit("job_update", job.to_dict())
                continue
            try:
                st = await asyncio.wait_for(conn.status(job.user), timeout=settings.connector_timeout_s)
            except (asyncio.TimeoutError, TimeoutError) as error:
                source_record_id = await claims.record_connector_error(name, job.entity_id, error)
                job.results[name] = {"status": "timed_out", "queried": False, "applicable": True, "availability": "unavailable", "reason": "connector status timed out", "error": "connector status timed out", "action": "retry refresh", "attempts": 0, "source_record_id": source_record_id}
                continue
            except Exception as error:
                source_record_id = await claims.record_connector_error(name, job.entity_id, error)
                safe_error = claims.connector_error_metadata(error)["connector_error"]
                job.results[name] = {"status": "failed", "queried": False, "applicable": True, "availability": "unavailable", "reason": "connector status unavailable", "error": f"{safe_error}: status unavailable", "action": "check connector configuration", "attempts": 0, "source_record_id": source_record_id}
                continue
            if not st.get("connected"):
                needs_key = bool(st.get("needs_key"))
                state = "credential-required" if needs_key else "unavailable"
                job.results[name] = {"status": "skipped", "queried": False, "applicable": True,
                                     "availability": state, "reason": st.get("detail") or "connector unavailable",
                                     "error": None, "action": "add credential" if needs_key else "retry refresh", "attempts": 0}
                await self._emit("job_update", job.to_dict())
                continue
            res = {"status": "running", "refresh_state": "refreshing", "queried": True, "applicable": True, "availability": "connected",
                   "facts": 0, "staged": 0, "committed": 0, "error": None, "attempts": 0,
                   "last_success_at": None, "cache": False, "simulated": False,
                   "retrieval_mode": job.retrieval_mode, "source_status": "not_attempted"}
            touched: dict[str, None] = {job.entity_id: None}
            job.results[name] = res
            facts = None
            connector_error = None
            for attempt in range(settings.connector_retries + 1):
                res["attempts"] = attempt + 1
                retrievals: list[dict] = []
                try:
                    with retrieval_context(job.retrieval_mode) as retrievals:
                        facts = await asyncio.wait_for(conn.enrich(entity, job.user), timeout=settings.connector_timeout_s)
                    if job.retrieval_mode == "operational_live":
                        validate_facts(name, facts)
                    res["status"] = "running"
                    res["error"] = None
                    res.pop("action", None)
                    if attempt:
                        res["recovered_after_attempts"] = attempt
                    break
                except (asyncio.TimeoutError, TimeoutError) as error:
                    facts = None
                    connector_error = error
                    res.update(status="timed_out", error="connector timed out", action="retry later; no fallback evidence was retrieved")
                except Exception as error:
                    # Validation happens after enrich returns. Never retain and
                    # process the assigned list when that validation rejects it.
                    facts = None
                    connector_error = error
                    safe_error = claims.connector_error_metadata(error)["connector_error"]
                    res.update(status="failed", error=f"{safe_error}: connector failed", action="check service availability and retry")
                finally:
                    self._apply_retrieval_result(res, retrievals)
                if attempt < settings.connector_retries:
                    await asyncio.sleep(min(2 ** attempt, 2))
            if facts is None and connector_error is not None:
                res["source_record_id"] = await claims.record_connector_error(name, job.entity_id, connector_error)
            if facts is not None:
                res["facts"] = len(facts)
                res["last_success_at"] = res.get("retrieved_at")
                for fact in facts:
                    if fact.artifact:
                        fact.artifact.props.setdefault("retrieval_status", res.get("source_status"))
                        fact.artifact.props.setdefault("retrieval_mode", job.retrieval_mode)
                        if res.get("cache_age_s") is not None:
                            fact.artifact.props.setdefault("cache_age_s", res["cache_age_s"])
                        if res.get("stale"):
                            fact.artifact.props.setdefault("stale", True)
                            fact.artifact.props.setdefault("fallback", True)
                res["simulated"] = any(
                    bool(f.props.get("simulated") or f.subject.props.get("simulated") or
                         (f.object and f.object.props.get("simulated")) or
                         (f.artifact and f.artifact.props.get("simulated")))
                    for f in facts
                )
                if not facts and res.get("source_status") == "no_retrieval":
                    res.update(status="empty", refresh_state="not_retrieved",
                               error=None,
                               warning="connector returned no facts without a source retrieval",
                               action="no new facts; source was not retrieved, so this is not a current result")
                elif not facts:
                    res.update(status="empty", action="no new facts; cached graph data is unchanged")
                else:
                    try:
                        await asyncio.wait_for(
                            self._process_facts(conn, facts, res, touched),
                            timeout=settings.connector_processing_timeout_s,
                        )
                        if res.get("fact_errors"):
                            stored = res["staged"] + res["committed"] + res.get("rejected", 0)
                            res.update(status="partial" if stored else "failed", error="one or more facts could not be stored",
                                       action="retry; successfully stored facts were preserved")
                        else:
                            res["status"] = "succeeded"
                    except (asyncio.TimeoutError, TimeoutError):
                        stored = res["staged"] + res["committed"] + res.get("rejected", 0)
                        res.update(
                            status="partial" if stored else "timed_out",
                            error="fact processing timed out",
                            action="retry; successfully stored facts were preserved",
                        )
            job.results[name] = res
            await self._checkpoint(job)
            await self._emit("job_update", job.to_dict())
            # Claims commit straight to the graph, so the canvas is told after every connector
            # rather than at the end of the job: facts appear as they are found.
            if res["committed"] or res["staged"] or res.get("rejected"):
                await events.announce(list(touched), reason=f"enrich:{name}", source="enrichment")
            if (
                name == "usaspending"
                and entity.get("kind") == "program"
                and res.get("status") in {"succeeded", "partial"}
                and (res.get("committed", 0) or res.get("staged", 0))
            ):
                await self._enqueue_supplier_enrichment(job)
            # entity may have gained identifiers (LEI, CIK…) that later connectors use
            rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": job.entity_id})
            if rows:
                entity = rows[0]["e"]
        await self._refresh_summary(job)

    async def _enqueue_supplier_enrichment(self, parent: Job) -> None:
        """Queue bounded, deduplicated enrichment for suppliers just discovered.

        Child jobs are ordinary durable jobs linked to the parent. They run after
        procurement discovery finishes and automatically select only sources that
        apply to each supplier's identifiers and context.
        """
        rows = await db.read(
            "MATCH (s:Entity)-[:SUPPLIES*1..2]->(p:Entity {id:$id}) "
            "WHERE s.kind='organization' AND coalesce(s.simulated,false)=false "
            "RETURN DISTINCT s.id AS id ORDER BY s.id LIMIT $limit",
            {"id": parent.entity_id, "limit": settings.supplier_enrichment_fanout},
        )
        child_ids: list[str] = []
        skipped = 0
        failed = 0
        for row in rows:
            supplier_id = row.get("id")
            if not supplier_id:
                continue
            if any(
                existing.entity_id == supplier_id and existing.status in {"queued", "running"}
                for existing in self.jobs.values()
            ):
                skipped += 1
                continue
            try:
                child = await self.enqueue(
                    supplier_id,
                    connectors=None,
                    user=parent.user,
                    requested_by="program-discovery",
                    retrieval_mode=parent.retrieval_mode,
                    parent_job_id=parent.id,
                )
                child_ids.append(child.id)
            except Exception:
                failed += 1
        parent.results["_supplier_enrichment"] = {
            "status": "queued" if child_ids else ("partial" if failed else "empty"),
            "queued": len(child_ids),
            "skipped_active": skipped,
            "failed_to_queue": failed,
            "child_job_ids": child_ids,
            "bounded_limit": settings.supplier_enrichment_fanout,
        }
        await self._checkpoint(parent)

    @staticmethod
    def _apply_retrieval_result(result: dict, retrievals: list[dict]) -> None:
        """Expose cache/live provenance without changing connector return types."""
        if not retrievals:
            result["source_status"] = "no_retrieval"
            result["refresh_state"] = "not_retrieved"
            return
        statuses = [item["source_status"] for item in retrievals]
        precedence = ("error", "fixture_miss", "stale_fallback", "offline_fixture", "live", "cached")
        result["source_status"] = next((status for status in precedence if status in statuses), statuses[-1])
        result["cache"] = any(status in {"cached", "offline_fixture", "stale_fallback"} for status in statuses)
        result["refresh_state"] = "stale-fallback" if "stale_fallback" in statuses else (
            "unavailable" if any(status in {"error", "fixture_miss"} for status in statuses) else "current"
        )
        result["retrievals"] = len(retrievals)
        ages = [item["cache_age_s"] for item in retrievals if item.get("cache_age_s") is not None]
        if ages:
            result["cache_age_s"] = round(max(ages), 3)
        retrieved = sorted(
            str(item["retrieved_at"]) for item in retrievals if item.get("retrieved_at")
        )
        if retrieved:
            # A connector may make multiple requests for one result. Use the
            # oldest backing response so freshness is conservative.
            result["retrieved_at"] = retrieved[0]
        if "stale_fallback" in statuses:
            result["stale"] = True
            result["fallback"] = True

    @staticmethod
    async def _checkpoint(job: Job) -> bool:
        try:
            await checkpoints.save(job)
            return True
        except Exception:
            # Do not discard already staged facts when the durability store is
            # temporarily unavailable; make the lack of a resumable checkpoint
            # visible in the job instead.
            job.results["_checkpoint_error"] = "checkpoint persistence unavailable; retry may re-run this source"
            return False
    async def _process_facts(self, conn, facts, res: dict, touched: dict[str, None]) -> None:
        res["rejected"] = 0
        res["fact_errors"] = 0
        for fact in facts:
            try:
                # Facts are the evidence boundary. Carry the retrieval policy
                # forward so readiness never mistakes fixture ingestion for a
                # successful operational refresh.
                fact.props.setdefault("retrieval_mode", res.get("retrieval_mode", "operational_live"))
                fact.props.setdefault("retrieval_status", res.get("source_status", "live"))
                fact.props.setdefault("cache", bool(res.get("cache")))
                fact.props.setdefault("fallback", bool(res.get("fallback")))
                if res.get("retrieved_at"):
                    fact.props["retrieved_at"] = res["retrieved_at"]
                if res.get("cache_age_s") is not None:
                    fact.props.setdefault("cache_age_s", res["cache_age_s"])
                if fact.artifact:
                    fact.artifact.props.setdefault("retrieval_mode", res.get("retrieval_mode", "operational_live"))
                    fact.artifact.props.setdefault("retrieval_status", res.get("source_status", "live"))
                    fact.artifact.props.setdefault("cache", bool(res.get("cache")))
                    fact.artifact.props.setdefault("fallback", bool(res.get("fallback")))
                    if res.get("retrieved_at"):
                        fact.artifact.props["retrieved_at"] = res["retrieved_at"]
                    if res.get("cache_age_s") is not None:
                        fact.artifact.props.setdefault("cache_age_s", res["cache_age_s"])
                model = fact.props.pop("_model", None) if "_model" in fact.props else None
                cid = await claims.stage(fact, source=conn.name, trust=conn.trust, model=model)
                res["staged"] += 1
                # stage() resolves refs before writing; invalidate the actual graph
                # endpoints so multi-hop additions reach open canvases immediately.
                touched[fact.subject.id] = None
                if fact.object:
                    touched[fact.object.id] = None
                status = await claims.decide(cid, trust=conn.trust)
                if status in ("committed", "rejected"):
                    res["staged"] -= 1
                    res[status] += 1
            except Exception:
                res["fact_errors"] += 1

    def _set_status(self, job: Job) -> None:
        states = [v.get("status") for k, v in job.results.items() if not k.startswith("_") and isinstance(v, dict)]
        successful = any(s in ("succeeded", "empty") for s in states)
        stored_result = any(
            v.get("staged", 0) + v.get("committed", 0) + v.get("rejected", 0) > 0
            for k, v in job.results.items() if not k.startswith("_") and isinstance(v, dict)
        )
        has_result = successful or stored_result
        unsuccessful = any(s in ("failed", "timed_out", "skipped", "not-applicable", "credential-required", "unavailable", "not_run", "partial") for s in states)
        if job.results.get("_error") and has_result:
            job.status = "partial"
        elif job.results.get("_error"):
            job.status = "failed"
        elif states and all(s == "empty" for s in states):
            job.status = "empty"
        elif job.results.get("_job_error") and has_result:
            job.status = "partial"
        elif job.results.get("_job_error") and not has_result:
            job.status = "timed_out"
        elif any(s in ("timed_out", "not_run") for s in states) and not has_result:
            job.status = "timed_out"
        elif unsuccessful and successful:
            job.status = "partial"
        elif any(s == "partial" for s in states):
            job.status = "partial"
        elif unsuccessful:
            job.status = "failed"
        elif not states:
            job.status = "empty"
        else:
            job.status = "succeeded"

    async def _refresh_summary(self, job: Job) -> None:
        job.summary_status = "running"
        try:
            from ..llm.client import has_key
            from ..llm.tasks import summarize_entity
            from ..report import build_report, deterministic_summary, persist_summary
            model_available = has_key(job.user)
            rep = await build_report(job.entity_id)
            if not rep:
                job.summary_status = "empty"
                return
            if not model_available:
                await persist_summary(
                    job.entity_id,
                    deterministic_summary(rep, "model_unavailable"),
                )
                job.summary_status = "unavailable"
                return
            out = await asyncio.wait_for(summarize_entity(job.user, rep), timeout=settings.summary_timeout_s)
            if out.get("generated_by") == "model-assisted":
                await persist_summary(job.entity_id, out)
                job.summary_updated = True
                job.summary_status = "succeeded"
            else:
                await persist_summary(job.entity_id, out)
                job.summary_status = "fallback"
        except (asyncio.TimeoutError, TimeoutError):
            await self._clear_summary_selection(job)
            job.summary_status = "timed_out"
            job.results["_summary_error"] = "model summary timed out; deterministic report remains available"
        except Exception as e:
            await self._clear_summary_selection(job)
            job.summary_status = "failed"
            safe_error = claims.connector_error_metadata(e)["connector_error"]
            job.results["_summary_error"] = f"{safe_error}: model summary unavailable; deterministic report remains available"

    async def _clear_summary_selection(self, job: Job) -> None:
        try:
            from ..report import clear_persisted_summary
            await clear_persisted_summary(job.entity_id)
        except Exception:
            job.results["_summary_cleanup_error"] = (
                "stale model summary metadata could not be cleared; retry after database recovery"
            )

    def list(self, limit: int = 50) -> list[dict]:
        return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]]


worker = Worker()
