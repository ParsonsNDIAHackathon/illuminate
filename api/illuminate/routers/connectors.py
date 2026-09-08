from __future__ import annotations

import asyncio

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..connectors import REGISTRY, get_connector
from ..connectors.base import diagnostic_failure
from ..connectors.http import HttpError
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


def _failure_for(error: Exception) -> dict:
    if isinstance(error, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return diagnostic_failure("timeout")
    status = error.status if isinstance(error, HttpError) else getattr(error, "status_code", None)
    if status in (401, 403):
        return diagnostic_failure("authentication")
    if status == 429:
        return diagnostic_failure("rate_limited")
    return diagnostic_failure("unavailable")


@router.post("/{name}/test")
async def test_connector(name: str, user: str = Depends(user_id)):
    connector = get_connector(name)
    if not connector:
        raise HTTPException(404, "unknown connector")
    if connector.key_name and not vault().get(user, connector.key_name):
        return diagnostic_failure("missing_credentials")
    try:
        return await asyncio.wait_for(connector.check_connectivity(user), timeout=10)
    except Exception as error:
        return _failure_for(error)
