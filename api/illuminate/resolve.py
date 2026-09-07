"""Entity resolution. UEI, CAGE and LEI carry most of it; the residue is fuzzy
matching on normalised names, and every fuzzy merge carries a confidence so a
false merge is visible rather than silent."""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from . import db
from .ids import name_match_score, normalize_name, normalize_person

FUZZY_ACCEPT = 93.0   # auto-accept threshold on token_set_ratio of normalised names
FUZZY_CANDIDATE = 80.0


@dataclass
class Match:
    id: str
    name: str
    method: str          # uei | cage | lei | name_exact | name_fuzzy
    confidence: float
    score: float | None = None


async def find_entity(*, uei: str | None = None, cage: str | None = None, lei: str | None = None, name: str | None = None) -> Match | None:
    """Return the best existing match, or None. Identifier hits are certain; name
    hits carry a graded confidence."""
    for key, val, conf in (("uei", uei, 1.0), ("lei", lei, 1.0), ("cage", cage, 0.98)):
        if val:
            rows = await db.read(f"MATCH (e:Entity) WHERE e.{key} = $v RETURN e.id AS id, e.name AS name LIMIT 1", {"v": val.upper()})
            if rows:
                return Match(rows[0]["id"], rows[0]["name"], key, conf)
    if not name:
        return None
    norm = normalize_name(name)
    if not norm:
        return None
    rows = await db.read("MATCH (e:Entity) WHERE e.name_norm = $n RETURN e.id AS id, e.name AS name LIMIT 1", {"n": norm})
    if rows:
        return Match(rows[0]["id"], rows[0]["name"], "name_exact", 0.9)
    # alias hit
    rows = await db.read("MATCH (e:Entity) WHERE $n IN coalesce(e.aliases_norm, []) RETURN e.id AS id, e.name AS name LIMIT 1", {"n": norm})
    if rows:
        return Match(rows[0]["id"], rows[0]["name"], "alias_exact", 0.85)
    # fuzzy over candidates sharing a leading token (cheap prefilter)
    first = norm.split(" ")[0]
    cands = await db.read(
        "MATCH (e:Entity) WHERE e.name_norm STARTS WITH $p RETURN e.id AS id, e.name AS name, e.name_norm AS norm LIMIT 200",
        {"p": first[:4]},
    )
    best, best_score = None, 0.0
    for c in cands:
        s = name_match_score(name, c["name"] or "")
        if s > best_score:
            best, best_score = c, s
    if best and best_score >= FUZZY_ACCEPT:
        return Match(best["id"], best["name"], "name_fuzzy", round(0.6 + 0.4 * (best_score - FUZZY_ACCEPT) / (100 - FUZZY_ACCEPT), 2), best_score)
    return None


async def fuzzy_candidates(name: str, limit: int = 5) -> list[dict]:
    norm = normalize_name(name)
    if not norm:
        return []
    cands = await db.read(
        "MATCH (e:Entity) WHERE e.name_norm CONTAINS $p RETURN e.id AS id, e.name AS name, e.name_norm AS norm LIMIT 300",
        {"p": norm.split(" ")[0][:5]},
    )
    scored = [(name_match_score(name, c["name"] or ""), c) for c in cands]
    scored = [(s, c) for s, c in scored if s >= FUZZY_CANDIDATE]
    scored.sort(key=lambda x: -x[0])
    return [{"id": c["id"], "name": c["name"], "score": s} for s, c in scored[:limit]]


async def find_person(name: str, *, source_ref: str | None = None) -> Match | None:
    """People are harder than companies: a name alone may be two people. Only an
    exact normalised-name hit (optionally with the same source ref) resolves."""
    norm = normalize_person(name)
    if not norm:
        return None
    if source_ref:
        rows = await db.read("MATCH (p:Person) WHERE p.source_ref = $r RETURN p.id AS id, p.name AS name LIMIT 1", {"r": source_ref})
        if rows:
            return Match(rows[0]["id"], rows[0]["name"], "source_ref", 0.98)
    rows = await db.read("MATCH (p:Person) WHERE p.name_norm = $n RETURN p.id AS id, p.name AS name LIMIT 1", {"n": norm})
    if rows:
        return Match(rows[0]["id"], rows[0]["name"], "name_exact", 0.7)
    return None
