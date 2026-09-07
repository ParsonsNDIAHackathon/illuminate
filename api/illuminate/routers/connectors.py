from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..connectors import REGISTRY, get_connector
from ..llm.client import check_key
from ..vault import vault
from .deps import user_id

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


class CredentialIn(BaseModel):
    value: str


@router.get("")
async def list_connectors(user: str = Depends(user_id)):
    out = []
    for c in REGISTRY:
        st = await c.status(user)
        out.append({**c.to_dict(), **st})
    return out


@router.put("/{name}/credential")
async def set_credential(name: str, body: CredentialIn, user: str = Depends(user_id)):
    c = get_connector(name)
    if not c or not c.key_name:
        raise HTTPException(404, "connector does not take a credential")
    if not body.value.strip():
        raise HTTPException(400, "empty credential")
    vault().set(user, c.key_name, body.value.strip())
    return {**c.to_dict(), **(await c.status(user))}


@router.delete("/{name}/credential")
async def delete_credential(name: str, user: str = Depends(user_id)):
    c = get_connector(name)
    if not c or not c.key_name:
        raise HTTPException(404, "connector does not take a credential")
    vault().delete(user, c.key_name)
    return {**c.to_dict(), **(await c.status(user))}


@router.post("/openai/check")
async def openai_check(user: str = Depends(user_id)):
    return await check_key(user)
