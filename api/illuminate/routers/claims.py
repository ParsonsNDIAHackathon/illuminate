from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import events
from ..enrichment import claims
from .deps import user_id

router = APIRouter(prefix="/api/claims", tags=["claims"])
ClaimStatus = Literal["staged", "committed", "rejected"]
MAX_PAGE_LIMIT = 500


class Note(BaseModel):
    note: str | None = None


@router.get("")
async def list_claims(
    status: ClaimStatus | None = None,
    entity_id: str | None = None,
    limit: int = Query(200, ge=1, le=MAX_PAGE_LIMIT),
    user: str = Depends(user_id),
):
    return await claims.list_claims(status, entity_id, limit)


@router.get("/source-records")
async def list_source_records(
    entity_id: str | None = None,
    limit: int = Query(200, ge=1, le=MAX_PAGE_LIMIT),
    user: str = Depends(user_id),
):
    return await claims.list_source_records(entity_id, limit)


@router.post("/{claim_id}/commit")
async def commit(claim_id: str, body: Note, user: str = Depends(user_id)):
    try:
        touched = await claims.endpoints(claim_id)
        status = await claims.commit(claim_id, body.note or f"approved by workspace user {user}")
    except KeyError:
        raise HTTPException(404, "no such claim")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    await events.announce(touched, reason="claim:commit", source="ui")
    return {"status": status}


@router.post("/{claim_id}/reject")
async def reject(claim_id: str, body: Note, user: str = Depends(user_id)):
    try:
        return {"status": await claims.reject(claim_id, body.note or f"rejected by workspace user {user}")}
    except KeyError:
        raise HTTPException(404, "no such claim")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
