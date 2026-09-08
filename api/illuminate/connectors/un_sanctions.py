"""UN Security Council Consolidated List — sanctions screening. Public XML, no key.

The UN list is the multilateral counterpart to OFAC's SDN: a US-clear vendor can still
sit on a UN designation, and a supply chain that crosses jurisdictions has to answer
both. One screen is recorded as a claim ('sanctions_screen' -> hit|clear) with the
matched designations as detail, exactly as the OFAC connector does.

The published URL 302s to a short-lived signed blob, so the fetch must follow redirects;
the cache key stays the canonical un.org URL, never the signed target.

The list carries two sections. ENTITIES are screened against organisations by the normal
enrichment path; INDIVIDUALS are indexed too and reachable through screen_person(), which
is what lets a named officer or director be checked rather than only their employer.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from ..ids import name_match_score, normalize_person
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import fetch_text

CONSOLIDATED_XML = "https://scsanctions.un.org/resources/xml/en/consolidated.xml"
LIST_PAGE = "https://www.un.org/securitycouncil/content/un-sc-consolidated-list"
# Organisation names are matched by the shared org scorer; person names are matched on
# sorted tokens, which is what survives the given/family-name reordering the list uses.
ORG_MATCH = 92
PERSON_MATCH = 90


def _names(node: ET.Element, alias_tag: str) -> list[str]:
    """A designation's primary name plus its aliases. Individuals split their name over
    FIRST_NAME..FOURTH_NAME; entities put the whole name in FIRST_NAME."""
    parts = [(node.findtext(t) or "").strip() for t in ("FIRST_NAME", "SECOND_NAME", "THIRD_NAME", "FOURTH_NAME")]
    primary = " ".join(p for p in parts if p)
    out = [primary] if primary else []
    for alias in node.findall(alias_tag):
        name = (alias.findtext("ALIAS_NAME") or "").strip()
        if name:
            out.append(name)
    return out


def _record(node: ET.Element, alias_tag: str) -> dict | None:
    names = _names(node, alias_tag)
    if not names:
        return None
    return {
        "dataid": (node.findtext("DATAID") or "").strip(),
        "name": names[0],
        "aliases": names[1:],
        "reference": (node.findtext("REFERENCE_NUMBER") or "").strip(),
        "regime": (node.findtext("UN_LIST_TYPE") or "").strip(),
        "listed_on": (node.findtext("LISTED_ON") or "").strip(),
        "comments": (node.findtext("COMMENTS1") or "").strip(),
    }


def parse(xml: str) -> dict:
    """Slim the 2MB list down to what a screen needs. Returns {generated, entities, individuals}."""
    root = ET.fromstring(xml)
    entities, individuals = [], []
    for node in root.findall("./ENTITIES/ENTITY"):
        rec = _record(node, "ENTITY_ALIAS")
        if rec:
            entities.append(rec)
    for node in root.findall("./INDIVIDUALS/INDIVIDUAL"):
        rec = _record(node, "INDIVIDUAL_ALIAS")
        if rec:
            rec["nationality"] = (node.findtext("./NATIONALITY/VALUE") or "").strip()
            individuals.append(rec)
    return {"generated": root.get("dateGenerated", ""), "entities": entities, "individuals": individuals}


async def consolidated_list() -> dict:
    return parse(await fetch_text(CONSOLIDATED_XML, ttl=86400))


def _hits(rows: list[dict], queries: list[str], threshold: float, score) -> list[dict]:
    found: list[dict] = []
    for row in rows:
        candidates = [row["name"], *row["aliases"]]
        best, matched = 0.0, ""
        for q in queries:
            for candidate in candidates:
                s = score(q, candidate)
                if s > best:
                    best, matched = s, candidate
        if best >= threshold:
            found.append({**row, "score": best, "matched_name": matched})
    found.sort(key=lambda h: h["score"], reverse=True)
    return found


def _person_score(a: str, b: str) -> float:
    from rapidfuzz import fuzz

    na, nb = normalize_person(a), normalize_person(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 100.0
    # A designation reduced to a single token matches far too much to be worth reporting.
    if len(na.split()) < 2 or len(nb.split()) < 2:
        return 0.0
    return fuzz.token_sort_ratio(na, nb)


def screen(name: str, aliases: list[str] | None = None, listing: dict | None = None) -> dict:
    """Screen an organisation against the ENTITIES section."""
    listing = listing or {}
    rows = listing.get("entities", [])
    queries = [n for n in [name, *(aliases or [])] if n]
    hits = _hits(rows, queries, ORG_MATCH, name_match_score)
    return {"result": "hit" if hits else "clear", "hits": hits[:10], "list_size": len(rows), "generated": listing.get("generated", "")}


def screen_person(name: str, aliases: list[str] | None = None, listing: dict | None = None) -> dict:
    """Screen a named individual against the INDIVIDUALS section."""
    listing = listing or {}
    rows = listing.get("individuals", [])
    queries = [n for n in [name, *(aliases or [])] if n]
    hits = _hits(rows, queries, PERSON_MATCH, _person_score)
    return {"result": "hit" if hits else "clear", "hits": hits[:10], "list_size": len(rows), "generated": listing.get("generated", "")}


def describe(res: dict, subject: str) -> str:
    if res["hits"]:
        return "; ".join(
            f"{h['matched_name']} [{h['reference']} · {h['regime']}, listed {h['listed_on']}] score {h['score']:.0f}"
            for h in res["hits"][:3]
        )
    return f"no match against {res['list_size']} UN Consolidated List {subject} (list generated {res['generated'] or 'unknown'})"


class UNSanctionsConnector(Connector):
    name = "un_sanctions"
    label = "UN Security Council Consolidated List"
    description = "UN sanctions designations — multilateral screen, complements OFAC SDN"
    trust = "authoritative"
    key_note = "No key. The consolidated XML is public and refreshed daily."

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        listing = await consolidated_list()
        res = screen(entity["name"], entity.get("aliases"), listing)
        subj = NodeRef("Entity", entity["id"])
        art = ArtifactRef(url=LIST_PAGE, title="UN Security Council Consolidated List", kind="record", source="UN Security Council")
        return [Fact(subj, "sanctions_screen", value=res["result"], artifact=art,
                     confidence=0.95 if res["result"] == "clear" else 0.8,
                     detail=describe(res, "entity designations"))]
