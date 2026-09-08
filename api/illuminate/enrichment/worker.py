"""Background enrichment. Runs unattended against connectors, so it needs a rule
rather than a prompt: it proposes claims and the trust rule in claims.py commits."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .. import db
from ..config import settings
from ..connectors import REGISTRY, get_connector
from . import claims

Listener = Callable[[str, dict], Awaitable[None]]


@dataclass
class Job:
    id: str
    entity_id: str
    entity_name: str | None
    connectors: list[str]
    user: str = "local"
    requested_by: str = "ui"
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

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def enqueue(self, entity_id: str, connectors: list[str] | None = None, user: str = "local", requested_by: str = "ui") -> Job:
        rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e.name AS name", {"id": entity_id})
        names = [c.name for c in REGISTRY if c.name not in ("openai",)] if connectors is None else connectors
        job = Job(id="job_" + uuid.uuid4().hex[:8], entity_id=entity_id, entity_name=rows[0]["name"] if rows else None, connectors=names, user=user, requested_by=requested_by)
        self.jobs[job.id] = job
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
                job.results["_error"] = f"{type(e).__name__}: job failed; retry or inspect service readiness"
                job.finished_at = time.time()
                await self._emit("job_update", job.to_dict())
            finally:
                self.queue.task_done()

    async def run(self, job: Job) -> None:
        job.status = "running"
        job.started_at = time.time()
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
            if job.summary_status == "not_requested":
                job.summary_status = "timed_out"
        except Exception as e:
            job.results["_error"] = f"{type(e).__name__}: job failed; retry or inspect service readiness"
        self._set_status(job)
        job.finished_at = time.time()
        await self._emit("job_update", job.to_dict())

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
            try:
                st = await asyncio.wait_for(conn.status(job.user), timeout=settings.connector_timeout_s)
            except (asyncio.TimeoutError, TimeoutError):
                job.results[name] = {"status": "timed_out", "error": "connector status timed out", "action": "retry later; cached graph data remains available", "attempts": 0}
                continue
            except Exception as e:
                job.results[name] = {"status": "failed", "error": f"{type(e).__name__}: status unavailable", "action": "check connector configuration", "attempts": 0}
                continue
            if not st.get("connected"):
                job.results[name] = {"status": "skipped", "error": st.get("detail") or "connector unavailable", "action": "configure the optional connector or continue with cached data", "attempts": 0}
                await self._emit("job_update", job.to_dict())
                continue
            res = {"status": "running", "facts": 0, "staged": 0, "committed": 0, "error": None, "attempts": 0}
            job.results[name] = res
            facts = None
            for attempt in range(settings.connector_retries + 1):
                res["attempts"] = attempt + 1
                try:
                    facts = await asyncio.wait_for(conn.enrich(entity, job.user), timeout=settings.connector_timeout_s)
                    res["status"] = "running"
                    res["error"] = None
                    res.pop("action", None)
                    if attempt:
                        res["recovered_after_attempts"] = attempt
                    break
                except (asyncio.TimeoutError, TimeoutError):
                    res.update(status="timed_out", error="connector timed out", action="retry later; cached graph data remains available")
                except Exception as e:
                    res.update(status="failed", error=f"{type(e).__name__}: connector failed", action="check service availability and retry")
                if attempt < settings.connector_retries:
                    await asyncio.sleep(min(2 ** attempt, 2))
            if facts is not None:
                res["facts"] = len(facts)
                if not facts:
                    res.update(status="empty", action="no new facts; cached graph data is unchanged")
                else:
                    try:
                        await asyncio.wait_for(
                            self._process_facts(conn, facts, res),
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
            await self._emit("job_update", job.to_dict())
            # entity may have gained identifiers (LEI, CIK…) that later connectors use
            rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": job.entity_id})
            if rows:
                entity = rows[0]["e"]
        await self._refresh_summary(job)

    async def _process_facts(self, conn, facts, res: dict) -> None:
        res["rejected"] = 0
        res["fact_errors"] = 0
        for fact in facts:
            try:
                model = fact.props.pop("_model", None) if "_model" in fact.props else None
                cid = await claims.stage(fact, source=conn.name, trust=conn.trust, model=model)
                res["staged"] += 1
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
        unsuccessful = any(s in ("failed", "timed_out", "skipped", "not_run", "partial") for s in states)
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
        try:
            from ..llm.client import has_key
            from ..llm.tasks import summarize_entity
            from ..report import build_report
            if not has_key(job.user):
                job.summary_status = "unavailable"
                return
            rep = await build_report(job.entity_id)
            if not rep:
                job.summary_status = "empty"
                return
            out = await asyncio.wait_for(summarize_entity(job.user, rep), timeout=settings.summary_timeout_s)
            if out:
                await db.write("MATCH (e:Entity {id:$id}) SET e.summary=$s, e.summary_model=$m, e.summary_at=$t",
                               {"id": job.entity_id, "s": out["summary"], "m": out["model"], "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                job.summary_updated = True
                job.summary_status = "succeeded"
            else:
                job.summary_status = "empty"
        except (asyncio.TimeoutError, TimeoutError):
            job.summary_status = "timed_out"
            job.results["_summary_error"] = "model summary timed out; deterministic report remains available"
        except Exception as e:
            job.summary_status = "failed"
            job.results["_summary_error"] = f"{type(e).__name__}: model summary unavailable; deterministic report remains available"

    def list(self, limit: int = 50) -> list[dict]:
        return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]]


worker = Worker()
