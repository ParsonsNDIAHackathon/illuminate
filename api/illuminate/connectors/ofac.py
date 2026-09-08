"""OFAC SDN list — sanctions screening. Open CSV, no key. The screen is recorded as
a claim ('sanctions_screen' → hit|clear) with the matched rows as detail.

The list designates both organisations and people. Entity enrichment screens the
organisation rows; screen_person() screens the individual rows, so a named officer
or director can be checked rather than only the company that employs them."""
from __future__ import annotations

import csv
import io

from rapidfuzz import fuzz

from ..ids import normalize_name, normalize_person
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import fetch_text

SDN_CSV = "https://www.treasury.gov/ofac/downloads/sdn.csv"
ALT_CSV = "https://www.treasury.gov/ofac/downloads/alt.csv"
MATCH = 92
PERSON_MATCH = 90


async def sdn_rows() -> list[dict]:
    text = await fetch_text(SDN_CSV, ttl=86400)
    rows = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 4:
            continue
        rows.append({"ent_num": r[0], "name": r[1], "type": r[2].strip(), "program": r[3].strip(), "remarks": r[11].strip() if len(r) > 11 else ""})
    return rows


async def screen_name(name: str, aliases: list[str] | None = None) -> dict:
    rows = await sdn_rows()
    names = [name] + list(aliases or [])
    norms = [normalize_name(n) for n in names if n]
    hits = []
    for r in rows:
        if _is_individual(r):
            continue
        rn = normalize_name(r["name"])
        if not rn:
            continue
        for n in norms:
            s = fuzz.token_sort_ratio(n, rn)
            if s >= MATCH and len(rn) > 5 and abs(len(n) - len(rn)) <= max(4, len(rn) // 3):
                hits.append({**r, "score": s, "matched": n})
                break
    return {"result": "hit" if hits else "clear", "hits": hits[:10], "list_size": len(rows)}


def _is_individual(row: dict) -> bool:
    return (row["type"] or "").strip().lower() == "individual"


async def screen_person(name: str, aliases: list[str] | None = None) -> dict:
    """Screen a named individual against the SDN's individual designations.

    Kept apart from screen_name because people and companies normalise differently:
    a legal-suffix stripper does nothing useful to a person's name, and a designation
    reduced to one token matches far too much to be worth reporting."""
    rows = [r for r in await sdn_rows() if _is_individual(r)]
    names = [n for n in [name, *(aliases or [])] if n]
    norms = [normalize_person(n) for n in names]
    hits = []
    for r in rows:
        rn = normalize_person(r["name"])
        if len(rn.split()) < 2:
            continue
        for n in norms:
            if len(n.split()) < 2:
                continue
            s = fuzz.token_sort_ratio(n, rn)
            if s >= PERSON_MATCH:
                hits.append({**r, "score": s, "matched": n})
                break
    hits.sort(key=lambda h: h["score"], reverse=True)
    return {"result": "hit" if hits else "clear", "hits": hits[:10], "list_size": len(rows)}


class OFACConnector(Connector):
    name = "ofac"
    label = "OFAC SDN"
    description = "Specially Designated Nationals — sanctions screen"
    trust = "authoritative"

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        res = await screen_name(entity["name"], entity.get("aliases"))
        subj = NodeRef("Entity", entity["id"])
        detail = ("; ".join(f"{h['name']} [{h['program']}] score {h['score']}" for h in res["hits"]) if res["hits"] else f"no match against {res['list_size']} SDN entries")
        art = ArtifactRef(url="https://sanctionssearch.ofac.treas.gov/", title="OFAC SDN list", kind="record", source="OFAC")
        return [Fact(subj, "sanctions_screen", value=res["result"], artifact=art, confidence=0.95 if res["result"] == "clear" else 0.8, detail=detail)]
