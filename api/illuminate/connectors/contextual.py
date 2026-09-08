"""Small, bounded, read-only adapters for contextual public sources."""
from __future__ import annotations

import re
from urllib.parse import quote

from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import fetch_document, fetch_json

_CVE = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
_FAR = re.compile(r"^(?:FAR\s*)?(52\.\d{3}-\d+)$", re.IGNORECASE)


def _values(entity: dict, singular: str, plural: str) -> list[str]:
    values = entity.get(plural)
    if values is None:
        values = entity.get(singular)
    if isinstance(values, str):
        values = re.split(r"[\s,;]+", values)
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _contains_far_clause(document: dict, clause: str) -> bool:
    """Do not turn a successful HTTP response into a clause-verification claim."""
    body = document.get("body")
    if not isinstance(body, bytes):
        return False
    text = body.decode("utf-8", errors="ignore").replace("\u00a0", " ")
    pieces = re.escape(clause).replace(r"\.", r"\s*\.\s*").replace(r"\-", r"\s*-\s*")
    return re.search(rf"(?<!\d){pieces}(?!\d)", text, flags=re.IGNORECASE) is not None


class OpenStreetMapConnector(Connector):
    name = "openstreetmap"
    label = "OpenStreetMap"
    description = "Reverse-geocoded map context for entities with explicit coordinates"
    trust = "open"
    kinds = ("organization", "program", "agency", "facility", "route")

    def applies_to(self, entity: dict) -> bool:
        return super().applies_to(entity) and entity.get("latitude") is not None and entity.get("longitude") is not None

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        if not self.applies_to(entity):
            return []
        lat, lon = float(entity["latitude"]), float(entity["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            return []
        data = await fetch_json("GET", "https://nominatim.openstreetmap.org/reverse", params={
            "lat": str(lat), "lon": str(lon), "format": "jsonv2", "zoom": "18",
        }, ttl=7 * 86400)
        osm_type, osm_id = data.get("osm_type"), data.get("osm_id")
        if not osm_type or osm_id is None:
            return []
        source_identifier = f"{osm_type}/{osm_id}"
        url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        artifact = ArtifactRef(url=url, title=str(data.get("display_name") or source_identifier),
                               kind="record", source="OpenStreetMap",
                               props={"source_identifier": source_identifier})
        return [Fact(NodeRef("Entity", entity["id"]), "location_context_screen",
                     value=source_identifier, artifact=artifact,
                     confidence=0.6, detail="Reverse-geocoded candidate at supplied coordinates")]


class FARConnector(Connector):
    name = "far"
    label = "FAR Part 52"
    description = "Verifies explicitly cited FAR Part 52 clauses against read-only eCFR"
    trust = "authoritative"
    kinds = ("organization", "program", "agency")

    def applies_to(self, entity: dict) -> bool:
        return super().applies_to(entity) and any(_FAR.match(value) for value in _values(entity, "far_clause", "far_clauses"))

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        clauses = []
        for value in _values(entity, "far_clause", "far_clauses"):
            match = _FAR.match(value)
            if match and match.group(1) not in clauses:
                clauses.append(match.group(1))
        facts: list[Fact] = []
        for clause in clauses[:5]:
            url = f"https://www.ecfr.gov/current/title-48/section-{quote(clause, safe='.-')}"
            document = await fetch_document(url, ttl=86400)
            if not _contains_far_clause(document, clause):
                continue
            artifact = ArtifactRef(url=url, title=f"FAR {clause}", kind="document", source="eCFR",
                                   props={"source_identifier": clause})
            facts.append(Fact(NodeRef("Entity", entity["id"]), "far_clause_screen",
                              value=clause, props={"clause": clause}, artifact=artifact,
                              confidence=1.0, detail="Clause citation retrieved from current eCFR"))
        return facts


class EPSSConnector(Connector):
    name = "epss"
    label = "FIRST EPSS"
    description = "Current EPSS scores for explicitly associated CVE identifiers"
    trust = "authoritative"
    kinds = ("organization", "program", "agency")

    def applies_to(self, entity: dict) -> bool:
        return super().applies_to(entity) and any(_CVE.match(value) for value in _values(entity, "cve", "cves"))

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        cves = []
        for value in _values(entity, "cve", "cves"):
            normalized = value.upper()
            if _CVE.match(normalized) and normalized not in cves:
                cves.append(normalized)
        if not cves:
            return []
        response = await fetch_json("GET", "https://api.first.org/data/v1/epss",
                                    params={"cve": ",".join(cves[:20])}, ttl=86400)
        facts: list[Fact] = []
        for record in response.get("data") or []:
            cve = str(record.get("cve") or "").upper()
            if cve not in cves:
                continue
            url = f"https://api.first.org/data/v1/epss?cve={quote(cve)}"
            artifact = ArtifactRef(url=url, title=f"EPSS score for {cve}", kind="record",
                                   source="FIRST", published_at=record.get("date"),
                                   props={"source_identifier": f"{cve}:{record.get('date') or 'current'}"})
            facts.append(Fact(NodeRef("Entity", entity["id"]), "vulnerability_screen",
                              value=str(record.get("epss")), props={
                                  "cve": cve, "percentile": record.get("percentile"),
                                  "as_of": record.get("date"),
                              }, artifact=artifact, confidence=1.0,
                              detail="Probability estimate; does not establish entity exposure"))
        return facts