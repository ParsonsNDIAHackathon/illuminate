from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from .. import events
from ..enrichment import claims, decisions
from ..report import build_report
from .deps import user_id

router = APIRouter(prefix="/api/claims", tags=["claims"])
ClaimStatus = Literal["staged", "committed", "rejected"]
MAX_PAGE_LIMIT = 500


class Note(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    note: str | None = Field(default=None, max_length=2000)


FindingId = Annotated[str, Field(min_length=14, max_length=180, pattern=r"^finding:risk:[A-Za-z0-9._:-]+$")]
EvidenceRef = Annotated[str, Field(min_length=5, max_length=160, pattern=r"^(clm_|art_)[A-Za-z0-9:_-]+$")]


class AnalystDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    disposition: Literal["investigate", "monitor", "seek_alternate_source", "accept_with_rationale", "close_no_action"]
    rationale: str = Field(min_length=3, max_length=2000)
    owner: str = Field(min_length=1, max_length=120)
    due_date: date | None = None
    program_id: str | None = Field(default=None, max_length=120)
    finding_ids: list[FindingId] = Field(min_length=1, max_length=100)
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, max_length=100)
    expected_version: int = Field(default=0, ge=0)


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
        status = await claims.commit(claim_id, body.note or "Approved after analyst review.", actor=user)
    except KeyError:
        raise HTTPException(404, "no such claim")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    await events.announce(touched, reason="claim:commit", source="ui")
    return {"status": status}


@router.post("/{claim_id}/reject")
async def reject(claim_id: str, body: Note, user: str = Depends(user_id)):
    try:
        return {"status": await claims.reject(claim_id, body.note or "Rejected after analyst review.", actor=user)}
    except KeyError:
        raise HTTPException(404, "no such claim")
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@router.get("/entities/{entity_id}/history")
async def entity_history(
    entity_id: str,
    program_id: str | None = None,
    limit: int = Query(200, ge=1, le=MAX_PAGE_LIMIT),
    user: str = Depends(user_id),
):
    try:
        return await decisions.history(entity_id, limit, program_id)
    except KeyError:
        raise HTTPException(404, "no such entity")


@router.post("/entities/{entity_id}/decisions", status_code=201)
async def record_entity_decision(entity_id: str, body: AnalystDecision, user: str = Depends(user_id)):
    try:
        report = await build_report(entity_id, body.program_id)
        if report is None:
            raise HTTPException(404, "no such entity")
        categories = report.get("risk", {}).get("categories") or []
        valid_findings = {
            f"finding:risk:{factor['rule_id']}"
            for category in categories
            for factor in category.get("factors") or []
            if factor.get("rule_id")
        }
        valid_findings.update(
            f"finding:risk:{category['id']}:evidence_gap"
            for category in categories
            if category.get("id") and not category.get("factors")
        )
        if not set(body.finding_ids).issubset(valid_findings):
            raise HTTPException(422, "finding scope is not present in the current vendor report")
        return await decisions.record(entity_id, actor=user, **body.model_dump(mode="json"))
    except HTTPException:
        raise
    except KeyError:
        raise HTTPException(404, "no such entity")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
