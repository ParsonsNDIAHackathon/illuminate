from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from neo4j.exceptions import ConstraintError
from pydantic import BaseModel, ConfigDict, Field, field_validator

from .. import db, events
from ..ids import normalize_name, stable_id
from .deps import user_id

router = APIRouter(prefix="/api/programs", tags=["programs"])


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


class ProgramCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    name: str = Field(min_length=2, max_length=160)
    agency: str | None = Field(default=None, max_length=160)
    program_code: str | None = Field(default=None, max_length=80)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = _clean(value)
        if not cleaned:
            raise ValueError("Program name is required")
        return cleaned

    @field_validator("agency", "program_code", "description")
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return _clean(value)


class Program(BaseModel):
    id: str
    name: str
    agency: str | None = None
    program_code: str | None = None
    description: str | None = None
    source: str
    created_at: str | None = None
    created_by: str | None = None


class ProgramList(BaseModel):
    items: list[Program]
    total: int
    limit: int
    offset: int


_RETURN = """
RETURN p.id AS id, p.name AS name, p.agency AS agency,
       p.program_code AS program_code, p.description AS description,
       coalesce(p.source, 'unknown') AS source, toString(p.created_at) AS created_at,
       p.created_by AS created_by
"""


@router.get("", response_model=ProgramList)
async def list_programs(
    q: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=100000),
):
    search = _clean(q)
    params = {
        "q": search.casefold() if search else None,
        "q_norm": normalize_name(search or "") or None,
        "limit": limit,
        "offset": offset,
    }
    where = (
        "p.kind = 'program' AND "
        "($q IS NULL OR toLower(p.name) CONTAINS $q OR p.name_norm CONTAINS $q_norm OR "
        "toLower(coalesce(p.program_code, '')) CONTAINS $q OR "
        "toLower(coalesce(p.agency, '')) CONTAINS $q)"
    )
    try:
        items = await db.read(
            f"MATCH (p:Entity) WHERE {where} {_RETURN} "
            "ORDER BY toLower(p.name), p.id SKIP $offset LIMIT $limit",
            params,
        )
        count = await db.read(f"MATCH (p:Entity) WHERE {where} RETURN count(p) AS total", params)
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Programs could not be loaded. Please try again.") from exc
    return {"items": items, "total": count[0]["total"] if count else 0, "limit": limit, "offset": offset}


@router.post("", response_model=Program, status_code=status.HTTP_201_CREATED)
async def create_program(payload: ProgramCreate, user: str = Depends(user_id)):
    now = datetime.now(timezone.utc).isoformat()
    params = {
        "id": stable_id("prog", "manual", normalize_name(payload.name)),
        "name": payload.name,
        "name_norm": normalize_name(payload.name),
        "agency": payload.agency,
        "program_code": payload.program_code,
        "program_code_norm": payload.program_code.casefold() if payload.program_code else None,
        "description": payload.description,
        "created_at": now,
        "created_by": user,
    }
    try:
        result = await db.write(
            """
            OPTIONAL MATCH (duplicate:Entity)
            WHERE duplicate.kind = 'program' AND
              (duplicate.name_norm = $name_norm OR
               ($program_code_norm IS NOT NULL AND
                toLower(coalesce(duplicate.program_code, '')) = $program_code_norm))
            WITH duplicate WHERE duplicate IS NULL
            CREATE (p:Entity {
              id: $id, kind: 'program', name: $name, name_norm: $name_norm,
              agency: $agency, program_code: $program_code,
              program_code_norm: $program_code_norm, description: $description,
              source: 'manual', method: 'user_entered', source_id: $id,
              created_at: datetime($created_at), created_by: $created_by,
              retrieved_at: $created_at, simulated: false
            })
            """
            + _RETURN,
            params,
        )
    except ConstraintError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A program with this name or program code already exists. Use a different name or code.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Program could not be saved. No record was created.") from exc
    rows = result.get("rows", [])
    if not rows:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A program with this name or program code already exists. Use a different name or code.",
        )
    await events.announce([rows[0]["id"]], reason="program:create", source="ui")
    return rows[0]