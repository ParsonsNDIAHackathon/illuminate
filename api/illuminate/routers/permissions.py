from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..tools.permissions import gate

router = APIRouter(prefix="/api/permissions", tags=["permissions"])


class ApproveIn(BaseModel):
    edited_statement: str | None = None
    edited_params: dict | None = None
    remember_shape: bool = False
    acknowledge_count: int | None = None


class RefuseIn(BaseModel):
    reason: str | None = None


@router.get("")
async def list_permissions():
    return {"pending": [r.model_dump() for r in gate.pending()], "history": [r.model_dump() for r in gate.history()]}


@router.post("/{request_id}/approve")
async def approve(request_id: str, body: ApproveIn):
    try:
        d = await gate.approve(request_id, edited_statement=body.edited_statement, edited_params=body.edited_params, remember_shape=body.remember_shape, acknowledge_count=body.acknowledge_count)
    except KeyError:
        raise HTTPException(404, "no such request")
    return d.model_dump()


@router.post("/{request_id}/refuse")
async def refuse(request_id: str, body: RefuseIn):
    try:
        d = await gate.refuse(request_id, body.reason)
    except KeyError:
        raise HTTPException(404, "no such request")
    return d.model_dump()
