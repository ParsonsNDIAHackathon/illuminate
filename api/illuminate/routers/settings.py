from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .. import db
from ..config import WorkspaceSettings, load_workspace, save_workspace, settings
from ..styles import PALETTE
from ..tools.contract import TOOLS

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/workspace")
async def get_workspace():
    ws = load_workspace()
    return {**ws.model_dump(), "defaults": {"model_strong": settings.model_strong, "model_fast": settings.model_fast}}


@router.put("/workspace")
async def put_workspace(body: WorkspaceSettings):
    if body.root_id:
        rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e.name AS name", {"id": body.root_id})
        if not rows:
            raise HTTPException(400, "root_id is not an entity")
        body.root_label = body.root_label or rows[0]["name"]
    return save_workspace(body).model_dump()


@router.get("/tools")
async def tools():
    return TOOLS


@router.get("/palette")
async def palette():
    return PALETTE
