"""Preset colour schemes over HTTP.

A scheme returns style_ops and a legend and writes nothing, for the same reason rescoring
and report generation do not go through the permission gate (routers/risk.py): it is a way
of drawing what is already in the graph. The canvas menu and the chat's apply_color_scheme
tool are the same call — the encoding cannot drift between them.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from .. import schemes

router = APIRouter(prefix="/api/styles", tags=["styles"])


class SchemeIn(BaseModel):
    #: Restrict to these nodes — normally what the canvas currently has drawn. Omitted, the
    #: scheme grades everything it can, which is what an outside agent with no canvas wants.
    ids: list[str] | None = None
    limit: int = schemes.MAX_NODES


@router.get("/schemes")
async def list_schemes():
    """The schemes on offer — what a 'colour by…' menu is built from."""
    return {"items": schemes.catalog()}


@router.get("/schemes/{name}")
async def get_scheme(name: str, limit: int = Query(schemes.MAX_NODES, le=schemes.MAX_NODES)):
    """Colour the whole graph by this scheme."""
    return await _apply(name, None, limit)


@router.post("/schemes/{name}")
async def apply_scheme(name: str, body: SchemeIn | None = None):
    """Colour these nodes by this scheme. A POST because the canvas sends its ids, not
    because anything is written."""
    body = body or SchemeIn()
    return await _apply(name, body.ids, body.limit)


async def _apply(name: str, ids: list[str] | None, limit: int):
    try:
        return await schemes.apply(name, ids, limit)
    except schemes.UnknownScheme:
        raise HTTPException(404, f"unknown scheme {name!r}; known schemes: {', '.join(schemes.SCHEMES)}")
