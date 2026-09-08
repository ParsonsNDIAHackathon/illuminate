"""Risk scoring endpoints.

A score is a derived property, not an assertion about the world, so it is not staged as a
claim and does not go through the permission gate: rescoring writes nothing a user could
not recompute from the graph in front of them. What it does write is announced, so open
canvases recolour without a reload.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import db, events, risk
from .deps import user_id

router = APIRouter(prefix="/api/risk", tags=["risk"])


class RescoreIn(BaseModel):
    ids: list[str] | None = None


@router.get("")
async def ranked(band: str | None = None, label: str | None = None, limit: int = Query(100, le=1000)):
    """The graph ordered by risk — the list a reviewer works down.

    Unscored nodes sort last rather than first: a null score means nothing was found to
    grade, which is a reason to enrich the node, not a reason to ignore it, so they are
    still returned and still counted.
    """
    where = ["(n:Entity OR n:Person)"]
    params: dict = {"limit": limit}
    if band:
        where.append("n.risk_band = $band")
        params["band"] = band
    if label:
        where.append(f"n:{'Person' if label.lower() == 'person' else 'Entity'}")
    rows = await db.read(
        f"""
        MATCH (n) WHERE {' AND '.join(where)}
        RETURN n.id AS id, n.name AS name, head(labels(n)) AS label, coalesce(n.kind, '') AS kind,
               n.risk_score AS score, n.risk_band AS band, n.risk_top_factor AS top_factor,
               n.risk_confidence AS confidence, n.risk_note AS note,
               n.risk_dimensions_scored AS dimensions_scored, n.risk_dimensions_requested AS dimensions_requested,
               n.risk_scored_at AS scored_at, coalesce(n.flagged, false) AS flagged,
               coalesce(n.simulated, false) AS simulated
        // Equal scores break on how much of the model answered, so a 100 built on two
        // dimensions sits below a 100 built on six.
        ORDER BY n.risk_score IS NULL, n.risk_score DESC, n.risk_confidence DESC, n.name
        LIMIT $limit
        """,
        params,
    )
    counts = await db.read(
        "MATCH (n) WHERE n:Entity OR n:Person "
        "RETURN coalesce(n.risk_band, 'unscored') AS band, count(*) AS n ORDER BY n DESC"
    )
    return {"items": rows, "bands": {r["band"]: r["n"] for r in counts},
            "weights": {k: v[0] for k, v in risk.DIMENSIONS.items()},
            "max_hops": risk.PROXIMITY_MAX_HOPS, "reference": risk.riskdata.refresh_note()}


@router.post("/rescore")
async def rescore(body: RescoreIn | None = None, user: str = Depends(user_id)):
    """Recompute and store. With no ids this is the whole graph, which is the normal
    case: proximity is a property of the network, so a designation that lands on one node
    changes the score of everything within reach of it."""
    ids = body.ids if body and body.ids else None
    summary = await risk.persist(ids)
    if ids:
        await events.announce(ids, reason="risk:rescore", source="ui")
    return summary


@router.get("/{node_id}")
async def explain(node_id: str):
    """The stored breakdown for one node: every dimension, its grading, its evidence and
    the ids to light up on the canvas."""
    out = await risk.explain(node_id)
    if not out:
        raise HTTPException(404, "no such node")
    return out
