"""Report endpoints.

Generating a report writes Report nodes and their REPORTS_ON / CITES edges without going
through the permission gate, for the reason rescoring does not either (routers/risk.py): a
report asserts nothing the graph does not already hold. It is a projection of committed
data, it is recomputable at any time from the graph in front of the user, and it only ever
happens because someone asked for it by name. What it writes is announced, so an open
canvas draws the report node beside its subject without a reload.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import reports
from .deps import user_id

router = APIRouter(prefix="/api/reports", tags=["reports"])


class GenerateIn(BaseModel):
    subject_id: str
    kind: str = reports.DEFAULT_KIND


@router.get("")
async def list_reports(limit: int = Query(100, le=500)):
    """Every report in the workspace, newest first — the Reports tab's whole query."""
    return {"items": await reports.list_reports(limit), "kinds": reports.kinds(), "default_kind": reports.DEFAULT_KIND}


@router.post("")
async def generate(body: GenerateIn, user: str = Depends(user_id)):
    """Build a report and store it. The id is stable per (kind, subject), so asking twice
    updates one node rather than growing a pile of near-identical documents."""
    try:
        return await reports.generate(body.kind, body.subject_id, user=user)
    except reports.ReportError as e:
        raise HTTPException(400, str(e))


@router.get("/{report_id}")
async def get_report(report_id: str, html: bool = True):
    """One report. The document is the payload here and nowhere else — it is stripped from
    every canvas payload (graphio.HEAVY_PROPS) — so `html=false` is for the properties card,
    which wants the metadata and the citations and would otherwise pull 100 KB to show a
    date and a button."""
    out = await reports.get_report(report_id, with_html=html)
    if not out:
        raise HTTPException(404, "no such report")
    return out


@router.post("/{report_id}/regenerate")
async def regenerate(report_id: str, user: str = Depends(user_id)):
    """Rebuild in place from current graph data: same node, same id, new generated_at.

    A report about a graph that keeps changing is only as good as its timestamp, so this is
    the button that matters most on a stored report.
    """
    existing = await reports.get_report(report_id, with_html=False)
    if not existing:
        raise HTTPException(404, "no such report")
    try:
        return await reports.generate(existing["kind"], existing["subject_id"], user=user)
    except reports.ReportError as e:
        raise HTTPException(400, str(e))


@router.delete("/{report_id}")
async def delete_report(report_id: str):
    if not await reports.delete_report(report_id):
        raise HTTPException(404, "no such report")
    return {"deleted": report_id}
