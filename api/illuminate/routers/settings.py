from __future__ import annotations

from fastapi import APIRouter

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
    return save_workspace(body).model_dump()


@router.get("/tools")
async def tools():
    return TOOLS


@router.get("/palette")
async def palette():
    return PALETTE
