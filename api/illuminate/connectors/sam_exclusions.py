"""SAM.gov Exclusions — public daily extract, no key, no quota.

The per-entity Exclusions API costs one request per vendor against a personal-key
budget of ~10/day. The same data is published every day as a public extract
(~170k records, 8k firms with UEIs). We download it once a day, keep a slim index
of firm and special-entity rows, and screen locally: UEI, then CAGE, then a strict
name match. Individuals and vessels are ignored."""
from __future__ import annotations

import csv
import gzip
import io
import json
import time
import zipfile
from pathlib import Path

import httpx

from ..config import settings
from ..ids import name_match_score, normalize_name
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import cache_dir, current_retrieval_mode, record_retrieval

LIST_URL = "https://sam.gov/api/prod/fileextractservices/v1/api/listfiles?domain=Exclusions/Public%20V2&privacy=Public"
DL_URL = "https://sam.gov/api/prod/fileextractservices/v1/api/download/Exclusions/Public%20V2/{name}?privacy=Public"
INDEX_NAME = "sam_exclusions_index.json.gz"
MAX_AGE_S = 36 * 3600
NAME_MATCH = 94

_index: dict | None = None
_index_mode: str | None = None


def _index_paths() -> list[Path]:
    # Committed fixture indexes are available only under explicit offline mode.
    if current_retrieval_mode() == "offline_fixture":
        return [cache_dir() / INDEX_NAME]
    return [settings.data_dir / INDEX_NAME]


async def _latest_extract_name() -> str | None:
    async with httpx.AsyncClient(timeout=60, follow_redirects=True, headers={"User-Agent": settings.illuminate_user_agent}) as c:
        r = await c.get(LIST_URL)
        r.raise_for_status()
        items = (r.json().get("_embedded") or {}).get("customS3ObjectSummaryList") or []
    names = sorted((i.get("displayKey") for i in items if i.get("displayKey", "").endswith(".ZIP")), reverse=True)
    return names[0] if names else None


def _slim(row: dict) -> dict | None:
    if row.get("Classification") not in ("Firm", "Special Entity Designation"):
        return None
    if row.get("Record Status") and row["Record Status"] != "Active":
        return None
    name = (row.get("Name") or "").strip()
    if not name:
        return None
    return {
        "name": name, "norm": normalize_name(name), "uei": (row.get("Unique Entity ID") or "").strip().upper() or None,
        "cage": (row.get("CAGE") or "").strip().upper() or None, "cls": row["Classification"], "agency": row.get("Excluding Agency"),
        "type": row.get("Exclusion Type"), "program": row.get("Exclusion Program"), "active": row.get("Active Date"), "ends": row.get("Termination Date"),
        "country": row.get("Country"), "sam": row.get("SAM Number"),
    }


async def refresh_index(force: bool = False) -> dict:
    """Download today's extract and write the slim index. Returns the index."""
    global _index, _index_mode
    target = _index_paths()[0]
    if not force and target.exists() and time.time() - target.stat().st_mtime < MAX_AGE_S:
        record_retrieval("offline_fixture" if current_retrieval_mode() == "offline_fixture" else "cached",
                         LIST_URL, age_s=max(0.0, time.time() - target.stat().st_mtime))
        return load_index()
    if current_retrieval_mode() == "offline_fixture":
        record_retrieval("fixture_miss", LIST_URL)
        raise FileNotFoundError("SAM exclusions index is not in the offline fixture store")
    name = await _latest_extract_name()
    if not name:
        raise RuntimeError("SAM extract listing returned no files")
    async with httpx.AsyncClient(timeout=300, follow_redirects=True, headers={"User-Agent": settings.illuminate_user_agent}) as c:
        r = await c.get(DL_URL.format(name=name))
        r.raise_for_status()
        blob = r.content
    rows: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        member = next(n for n in z.namelist() if n.upper().endswith(".CSV"))
        with z.open(member) as fh:
            reader = csv.DictReader(io.TextIOWrapper(fh, encoding="latin-1", newline=""))
            for row in reader:
                s = _slim(row)
                if s:
                    rows.append(s)
    idx = {"extract": name, "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "total_records": reader.line_num, "rows": rows}
    payload = gzip.compress(json.dumps(idx).encode())
    for p in _index_paths():
        try:
            p.write_bytes(payload)
        except Exception:
            pass
    _index = idx
    _index_mode = current_retrieval_mode()
    record_retrieval("live", LIST_URL, age_s=0)
    return idx


def load_index() -> dict:
    global _index, _index_mode
    mode = current_retrieval_mode()
    if _index is not None and _index_mode == mode:
        return _index
    for p in _index_paths():
        if p.exists():
            _index = json.loads(gzip.decompress(p.read_bytes()))
            _index_mode = mode
            return _index
    raise FileNotFoundError("no SAM exclusions index; run refresh_index()")


def screen(name: str, uei: str | None = None, cage: str | None = None, aliases: list[str] | None = None) -> dict:
    idx = load_index()
    rows = idx["rows"]
    hits: list[dict] = []
    if uei:
        hits += [{**r, "matched_on": "uei", "score": 100} for r in rows if r["uei"] == uei.upper()]
    if cage and not hits:
        hits += [{**r, "matched_on": "cage", "score": 100} for r in rows if r["cage"] == cage.upper()]
    if not hits:
        names = [name] + list(aliases or [])
        norms = {normalize_name(n) for n in names if n}
        first_tokens = {n.split(" ")[0] for n in norms if n}
        for r in rows:
            if not r["norm"] or r["norm"].split(" ")[0] not in first_tokens:
                continue  # cheap prefilter: share the first token
            best = max((name_match_score(n, r["name"]) for n in names if n), default=0)
            if best >= NAME_MATCH:
                hits.append({**r, "matched_on": "name", "score": best})
    return {"result": "hit" if hits else "clear", "hits": hits[:10], "extract": idx["extract"], "index_size": len(rows)}


class SAMExclusionsConnector(Connector):
    name = "sam_exclusions"
    label = "SAM.gov Exclusions (public extract)"
    description = "Debarment / suspension / ineligibility — daily public extract, screened locally"
    trust = "authoritative"
    key_note = "No key. The extract is refreshed daily from sam.gov Data Services."

    async def status(self, user: str) -> dict:
        try:
            idx = load_index()
            return {"connected": True, "detail": f"extract {idx['extract'][-9:-4]} · {len(idx['rows'])} firm/SED records", "needs_key": False}
        except FileNotFoundError:
            return {"connected": True, "detail": "no key required · extract downloads on first use", "needs_key": False}

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        try:
            await refresh_index()
        except Exception as e:
            try:
                paths = _index_paths()
                age = max(0.0, time.time() - paths[0].stat().st_mtime)
                if current_retrieval_mode() != "offline_fixture" and age > settings.connector_cache_fallback_max_age_s:
                    raise FileNotFoundError("cached SAM exclusions index is beyond fallback age")
                load_index()
                record_retrieval("offline_fixture" if current_retrieval_mode() == "offline_fixture" else "stale_fallback",
                                 LIST_URL, age_s=age)
            except FileNotFoundError:
                raise RuntimeError(f"SAM exclusions extract unavailable: {e}")
        res = screen(entity["name"], entity.get("uei"), entity.get("cage"), entity.get("aliases"))
        subj = NodeRef("Entity", entity["id"])
        art = ArtifactRef(url="https://sam.gov/data-services/Exclusions/Public%20V2?privacy=Public", title=f"SAM.gov exclusions public extract {res['extract']}", kind="record", source="SAM.gov")
        if res["hits"]:
            detail = "; ".join(f"{h['name']} — {h['type']} by {h['agency']} ({h['matched_on']} {h['score']:.0f}, active {h['active']})" for h in res["hits"][:3])
            conf = 0.98 if res["hits"][0]["matched_on"] in ("uei", "cage") else 0.8
        else:
            detail = f"no active exclusion matched by UEI/CAGE/name against {res['index_size']} firm and special-entity records ({res['extract']})"
            conf = 0.95 if entity.get("uei") else 0.85
        return [Fact(subj, "exclusion_screen", value=res["result"], artifact=art, confidence=conf, detail=detail)]
