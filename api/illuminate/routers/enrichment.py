from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..enrichment.worker import worker
from .deps import user_id

router = APIRouter(prefix="/api", tags=["enrichment"])


class EnrichIn(BaseModel):
    connectors: list[str] | None = None


@router.post("/enrich/{entity_id}")
async def enrich(entity_id: str, body: EnrichIn | None = None, user: str = Depends(user_id)):
    job = await worker.enqueue(entity_id, connectors=(body.connectors if body else None), user=user, requested_by="ui")
    return job.to_dict()


@router.get("/jobs")
async def jobs():
    return worker.list()


@router.get("/jobs/{job_id}")
async def job(job_id: str):
    j = worker.jobs.get(job_id)
    if not j:
        raise HTTPException(404, "no such job")
    return j.to_dict()
