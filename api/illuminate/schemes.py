"""Preset colour schemes — a named encoding the server already knows how to draw.

The style contract (styles.py) lets anything paint the canvas an op at a time, and the
chat uses it to invent encodings on the spot. A *scheme* is the opposite end: an encoding
that is asked for often enough that working it out from scratch each time is wasted
tokens and an invitation to drift — "colour by risk" should look the same on Tuesday as
it did on Monday, and should not depend on the model remembering which swatch means
severe.

So a scheme owns two things: the query that decides which node lands in which bucket, and
the ramp that gives the bucket a colour. Both live here, once, and the chat, the canvas
menu and any outside agent over MCP all get the same picture. The output is ordinary
style_ops — nothing downstream needs to know a scheme was involved.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from . import db, risk
from .styles import derive_legend, validate_ops

# How many nodes one scheme will colour in a pass. Style ops are replayed on every canvas
# sync (web/src/stores/graph.ts), so the ramp is bounded like everything else that paints.
MAX_NODES = 2000


@dataclass
class Scheme:
    name: str
    label: str
    description: str
    #: id -> bucket rows, fetched from the graph. Given the ids to restrict to, or None for
    #: everything the scheme can grade.
    fetch: Callable[[list[str] | None, int], Awaitable[list[dict]]]
    #: rows -> ordered style ops. Pure, so the ramp is testable without a database.
    ops: Callable[[list[dict]], list[dict]]
    #: rows -> a sentence about what was and was not coloured, for whoever asked.
    note: Callable[[list[dict]], str]


# --- risk: a red → green ramp over the stored score --------------------------------
#
# Two things this ramp must not do:
#
#  1. Paint an unscored node green. A null score means the scorer found nothing to grade,
#     which is a reason to enrich the node, not an all-clear — so unscored nodes get a
#     dashed neutral outline that is visibly off the ramp, never its safe end. This is the
#     same rule web/src/styles/risk.ts keeps for the halo.
#  2. Invent thresholds. The bands are risk.BANDS, the ones the Risk tab, the band chips
#     and the report all sort by, so a node that reads "severe" in a list reads red here.
#
# The band-to-swatch mapping is deliberately *not* the one in styles/risk.ts: that module
# paints low neutral, because a low score usually means "screened clear on the little we
# asked". A scheme called "risk gradient" is asked for as a gradient, so low is the green
# end here — the reading is "least concern of what we could grade", and unscored stays out
# of it entirely.
RISK_RAMP: list[tuple[str, str, str]] = [
    # band, swatch, legend label
    ("severe", "red", "Severe (75+)"),
    ("high", "orange", "High (50–74)"),
    ("elevated", "yellow", "Elevated (25–49)"),
    ("low", "green", "Low (0–24)"),
]

_RISK_CYPHER = """
MATCH (n) WHERE (n:Entity OR n:Person) {filter}
RETURN n.id AS id, n.risk_score AS score, n.risk_band AS band, n.risk_confidence AS confidence
ORDER BY n.risk_score IS NULL, n.risk_score DESC
LIMIT $limit
"""


async def _fetch_risk(ids: list[str] | None, limit: int) -> list[dict]:
    # None and [] are different questions: no ids means "everything you can grade", an empty
    # list means "these nodes", of which there are none. A canvas with nothing on it must not
    # come back having coloured the whole graph.
    filt = "AND n.id IN $ids" if ids is not None else ""
    return await db.read(_RISK_CYPHER.format(filter=filt), {"ids": ids or [], "limit": limit})


def _risk_ops(rows: list[dict]) -> list[dict]:
    """Bucket by band, most concerning first, so the legend reads down the ramp."""
    buckets: dict[str, list[str]] = {b: [] for b, _, _ in RISK_RAMP}
    unscored: list[str] = []
    for r in rows:
        score = r.get("score")
        # The stored band is authoritative when present; a score with no band (an older
        # write, a hand-set property) is graded rather than dropped.
        band = r.get("band") or risk.band(score)
        if score is None or band not in buckets:
            unscored.append(r["id"])
        else:
            buckets[band].append(r["id"])
    ops = [
        {"op": "set", "ids": ids, "style": {"fill": swatch}, "label": label}
        for band, swatch, label in RISK_RAMP
        if (ids := buckets[band])
    ]
    if unscored:
        # Outlined, not filled: absence of a grade is marked, not ranked.
        ops.append({"op": "set", "ids": unscored, "style": {"stroke": "neutral", "dashed": True},
                    "label": "Unscored — nothing to grade"})
    return ops


def _risk_note(rows: list[dict]) -> str:
    scored = [r for r in rows if r.get("score") is not None]
    thin = [r for r in scored if (r.get("confidence") or 0) < 60]
    parts = [f"{len(scored)} scored node(s) coloured red (severe) through green (low)"]
    if len(rows) - len(scored):
        parts.append(f"{len(rows) - len(scored)} unscored, outlined rather than coloured — "
                     "nothing was found to grade them on, which is not the same as low risk")
    if thin:
        parts.append(f"{len(thin)} scored on under 60% of the model, so those colours are thin")
    return "; ".join(parts) + "."


SCHEMES: dict[str, Scheme] = {
    "risk": Scheme(
        name="risk",
        label="Risk",
        description="Colour every scored entity and person by its risk band, red (severe) "
                    "through green (low). Unscored nodes are outlined, never coloured.",
        fetch=_fetch_risk,
        ops=_risk_ops,
        note=_risk_note,
    ),
}


def catalog() -> list[dict]:
    return [{"name": s.name, "label": s.label, "description": s.description} for s in SCHEMES.values()]


class UnknownScheme(KeyError):
    pass


async def apply(name: str, ids: list[str] | None = None, limit: int = MAX_NODES) -> dict[str, Any]:
    """Build one scheme's style_ops and legend. Reads only — a scheme is a way of drawing
    the graph, not a change to it, so nothing here goes through the permission gate."""
    scheme = SCHEMES.get((name or "").strip().lower())
    if not scheme:
        raise UnknownScheme(name)
    rows = await scheme.fetch(ids, max(1, min(int(limit or MAX_NODES), MAX_NODES)))
    ops = validate_ops(scheme.ops(rows))
    dumped = [o.model_dump(exclude_none=True) for o in ops]
    return {
        "scheme": scheme.name,
        "label": scheme.label,
        "style_ops": dumped,
        "legend": [l.model_dump() for l in derive_legend(ops)],
        "node_count": len(rows),
        "note": scheme.note(rows),
    }
