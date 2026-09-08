from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..enrichment.worker import worker
from ..tools.handlers import ToolContext, discover_suppliers
from .deps import user_id

router = APIRouter(prefix="/api", tags=["enrichment"])


class EnrichIn(BaseModel):
    connectors: list[str] | None = None


class DiscoverIn(BaseModel):
    keywords: list[str]
    agency: str | None = None
    since: str | None = None
    until: str | None = None
    max_primes: int | None = None
    max_subs: int | None = None


@router.post("/enrich/{entity_id}")
async def enrich(entity_id: str, body: EnrichIn | None = None, user: str = Depends(user_id)):
    job = await worker.enqueue(entity_id, connectors=(body.connectors if body else None), user=user, requested_by="ui")
    return job.to_dict()


@router.post("/programs/{entity_id}/suppliers")
async def discover(entity_id: str, body: DiscoverIn, user: str = Depends(user_id)):
    """Award-search a program into a supplier network. Same handler the chat and MCP
    tool use, so the write is previewed and approved the same way — this call blocks
    until the user decides."""
    ctx = ToolContext.from_workspace(source="ui", user=user)
    res = await discover_suppliers(ctx, entity_id, **body.model_dump())
    if not res.ok:
        raise HTTPException(400, res.data.get("error") or "discovery refused")
    return {"data": res.data, "permission": res.permission}


@router.get("/jobs")
async def jobs():
    return worker.list()


@router.get("/jobs/{job_id}")
async def job(job_id: str):
    j = worker.jobs.get(job_id)
    if not j:
        raise HTTPException(404, "no such job")
    return j.to_dict()
