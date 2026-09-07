from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..cypher.templates import TEMPLATES
from ..cypher.validator import CypherRejected, validate
from ..tools.handlers import ToolContext, run_cypher, run_template, set_styles
from .deps import user_id

router = APIRouter(prefix="/api/query", tags=["query"])


class CypherIn(BaseModel):
    statement: str
    params: dict = {}
    rationale: str | None = None


class TemplateIn(BaseModel):
    name: str
    params: dict = {}
    apply_styles: bool = True


class StyleIn(BaseModel):
    ops: list[dict]


def _out(r):
    return {"ok": r.ok, "data": r.data, "cypher": r.cypher, "params": r.params, "subgraph": r.subgraph, "style_ops": r.style_ops, "legend": r.legend, "permission": r.permission, "notes": r.notes}


@router.get("/templates")
async def templates():
    return [{"name": t.name, "description": t.description, "schema": t.schema()} for t in TEMPLATES.values()]


@router.post("/validate")
async def validate_stmt(body: CypherIn):
    try:
        v = validate(body.statement, params=dict(body.params))
        return {"ok": True, "classification": v.classification, "statement": v.statement, "labels": sorted(v.labels), "rel_types": sorted(v.rel_types), "notes": v.notes}
    except CypherRejected as e:
        return {"ok": False, "reason": e.reason}


@router.post("/cypher")
async def cypher(body: CypherIn, user: str = Depends(user_id)):
    ctx = ToolContext.from_workspace(source="ui", user=user)
    return _out(await run_cypher(ctx, body.statement, body.params, body.rationale))


@router.post("/template")
async def template(body: TemplateIn, user: str = Depends(user_id)):
    ctx = ToolContext.from_workspace(source="ui", user=user)
    return _out(await run_template(ctx, body.name, body.params, body.apply_styles))


@router.post("/styles")
async def styles(body: StyleIn, user: str = Depends(user_id)):
    ctx = ToolContext.from_workspace(source="ui", user=user)
    return _out(await set_styles(ctx, body.ops))
