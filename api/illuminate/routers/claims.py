from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..enrichment import claims

router = APIRouter(prefix="/api/claims", tags=["claims"])


class Note(BaseModel):
    note: str | None = None


@router.get("")
async def list_claims(status: str | None = None, entity_id: str | None = None, limit: int = 200):
    return await claims.list_claims(status, entity_id, limit)


@router.get("/source-records")
async def list_source_records(entity_id: str | None = None, limit: int = 200):
    return await claims.list_source_records(entity_id, limit)


@router.post("/{claim_id}/commit")
async def commit(claim_id: str, body: Note):
    try:
        return {"status": await claims.commit(claim_id, body.note or "approved by user")}
    except KeyError:
        raise HTTPException(404, "no such claim")


@router.post("/{claim_id}/reject")
async def reject(claim_id: str, body: Note):
    return {"status": await claims.reject(claim_id, body.note or "rejected by user")}
