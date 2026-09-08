"""Background enrichment. Runs unattended against connectors, so it needs a rule
rather than a prompt: it proposes claims and the trust rule in claims.py commits."""
from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .. import db, events
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
    status: str = "queued"           # queued | running | done | failed
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    results: dict = field(default_factory=dict)   # connector -> {facts, staged, committed, error}
    summary_updated: bool = False

    def to_dict(self) -> dict:
        return self.__dict__.copy()


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
        names = connectors or [c.name for c in REGISTRY if c.name not in ("openai",)]
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
                job.results["_error"] = str(e)
                job.finished_at = time.time()
                await self._emit("job_update", job.to_dict())

    async def run(self, job: Job) -> None:
        job.status = "running"
        job.started_at = time.time()
        await self._emit("job_update", job.to_dict())
        rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": job.entity_id})
        if not rows:
            job.status = "failed"
            job.results["_error"] = "entity not found"
            job.finished_at = time.time()
            await self._emit("job_update", job.to_dict())
            return
        entity = rows[0]["e"]
        for name in job.connectors:
            conn = get_connector(name)
            if not conn:
                job.results[name] = {"error": "unknown connector"}
                continue
            if not conn.applies_to(entity):
                job.results[name] = {"skipped": f"source does not speak about a {entity.get('kind') or 'organization'}"}
                await self._emit("job_update", job.to_dict())
                continue
            st = await conn.status(job.user)
            if not st.get("connected"):
                job.results[name] = {"skipped": st.get("detail")}
                await self._emit("job_update", job.to_dict())
                continue
            res = {"facts": 0, "staged": 0, "committed": 0, "error": None}
            touched: dict[str, None] = {job.entity_id: None}
            try:
                facts = await conn.enrich(entity, job.user)
                res["facts"] = len(facts)
                for f in facts:
                    cid = await claims.stage(f, source=conn.name, trust=conn.trust, model=f.props.pop("_model", None) if "_model" in f.props else None)
                    status = await claims.decide(cid, trust=conn.trust)
                    res["staged" if status == "staged" else "committed"] += 1
                    # stage() rewrites the refs to whatever they resolved to, so these are
                    # the ids the write actually touched — a supplier network reaches the
                    # canvas whole rather than one hop from the entity being enriched.
                    touched[f.subject.id] = None
                    if f.object:
                        touched[f.object.id] = None
            except Exception as e:
                res["error"] = f"{type(e).__name__}: {e}"
            job.results[name] = res
            await self._emit("job_update", job.to_dict())
            # Claims commit straight to the graph, so the canvas is told after every connector
            # rather than at the end of the job: facts appear as they are found.
            if res["committed"] or res["staged"]:
                await events.announce(list(touched), reason=f"enrich:{name}", source="enrichment")
            # entity may have gained identifiers (LEI, CIK…) that later connectors use
            rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": job.entity_id})
            entity = rows[0]["e"]
        await self._rescore(job)
        await self._refresh_summary(job)
        job.status = "done"
        job.finished_at = time.time()
        await self._emit("job_update", job.to_dict())
        await events.announce([job.entity_id], reason="enrich:done", source="enrichment")

    async def _rescore(self, job: Job) -> None:
        """Rescore the whole graph, not just the entity that was enriched.

        A screen that lands on one vendor changes what everything within three hops of it
        is exposed to, and those neighbours are exactly the nodes nobody thought to look
        at. Scoring only the enriched entity would hide the finding this feature exists
        to surface. The pass is a handful of bulk queries, so it is cheaper than the
        enrichment that preceded it.
        """
        try:
            from ..risk import persist
            job.results["_risk"] = await persist()
        except Exception as e:
            job.results["_risk_error"] = f"{type(e).__name__}: {e}"

    async def _refresh_summary(self, job: Job) -> None:
        try:
            from ..llm.client import has_key
            from ..llm.tasks import summarize_entity
            from ..report import build_report
            if not has_key(job.user):
                return
            rep = await build_report(job.entity_id)
            if not rep:
                return
            out = await summarize_entity(job.user, rep)
            if out:
                await db.write("MATCH (e:Entity {id:$id}) SET e.summary=$s, e.summary_model=$m, e.summary_at=$t",
                               {"id": job.entity_id, "s": out["summary"], "m": out["model"], "t": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
                job.summary_updated = True
        except Exception as e:
            job.results["_summary_error"] = str(e)

    def list(self, limit: int = 50) -> list[dict]:
        return [j.to_dict() for j in sorted(self.jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]]


worker = Worker()
