"""Pre-seed one real program's graph so the live demo runs against warm data.

    python -m illuminate.seed.seed --program "V-22" --scenario
    python -m illuminate.seed.seed --offline        # rebuild from committed fixtures

Sources: USAspending (primes, subawards, recipients, competition), GLEIF (LEI,
jurisdiction, parents), OFAC SDN (sanctions screen), LittleSis (people), EDGAR
(listed parents). Every HTTP response is cached under seed/fixtures so the graph
rebuilds offline. --scenario adds a clearly-labelled simulated adversarial tie,
because the brief asks for one and real data rarely volunteers it.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import defaultdict
from pathlib import Path

from .. import db
from ..connectors import get_connector
from ..connectors.base import now_iso
from ..connectors.registry import source_metadata
from ..connectors.usaspending import award_detail, award_url, is_sole_source, psc_category, recipient, recipient_url, search_awards
from ..enrichment import claims
from ..ids import edge_id, entity_id, location_id, normalize_name, person_id, artifact_id, stable_id
from ..schema import ensure_schema

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CATALOG_FIXTURE = FIXTURES / "catalog_lineage.json"
PROV = {"source": "USAspending", "method": "connector", "confidence": 0.95}
SEED_VERSION = "uc7-fixtures-v1"
_seed_retrieval_mode = "offline_fixture"
_seed_retrieval_trace: list[dict] | None = None
from ..config import settings
from ..connectors.http import retrieval_context, set_cache_dir


def log(msg: str) -> None:
    print(f"[seed {time.strftime('%H:%M:%S')}] {msg}", flush=True)

def _with_retrieval_truth(props: dict, retrievals: list[dict] | None = None) -> dict:
    """Attach the conservative truth of every response backing a seed record."""
    result = dict(props)
    if result.get("source") != "USAspending":
        return result
    outcomes = retrievals if retrievals is not None else (
        _seed_retrieval_trace[-1:] if _seed_retrieval_trace else []
    )
    statuses = [item.get("source_status") for item in outcomes]
    precedence = ("error", "fixture_miss", "stale_fallback", "offline_fixture", "cached", "live")
    source_status = next((status for status in precedence if status in statuses), "unknown")
    result["retrieval_mode"] = _seed_retrieval_mode
    result["source_status"] = source_status
    result["retrieval_status"] = result["source_status"]
    result["cache"] = result["source_status"] in {"cached", "stale_fallback"}
    result["fallback"] = result["source_status"] == "stale_fallback"
    ages = [item["cache_age_s"] for item in outcomes if item.get("cache_age_s") is not None]
    if ages:
        result["cache_age_s"] = max(ages)
    retrieved = sorted(str(item["retrieved_at"]) for item in outcomes if item.get("retrieved_at"))
    if retrieved:
        result["retrieved_at"] = retrieved[0]
    return result
async def reset_graph() -> None:
    await db.write("MATCH (n) WHERE NOT n:Category DETACH DELETE n")
    log("graph reset (categories kept)")


async def merge_entity(eid: str, props: dict, *, retrievals: list[dict] | None = None) -> None:
    props = _with_retrieval_truth({k: v for k, v in props.items() if v is not None}, retrievals)
    props.setdefault("retrieval_mode", _seed_retrieval_mode)
    retrieved_at = props.pop("retrieved_at", None) or now_iso()
    ingested_at = now_iso()
    await db.write(
        "MERGE (e:Entity {id:$id}) "
        "ON CREATE SET e.retrieved_at=$retrieved, e.first_ingested_at=$ingested "
        "SET e += $p, e.retrieved_at=coalesce(e.retrieved_at,$retrieved), "
        "e.latest_retrieved_at=$retrieved, "
        "e.first_ingested_at=coalesce(e.first_ingested_at,$ingested), "
        "e.last_ingested_at=$ingested, e.name_norm=coalesce(e.name_norm,$nn)",
        {
            "id": eid,
            "p": props,
            "nn": normalize_name(props.get("name", "")),
            "retrieved": retrieved_at,
            "ingested": ingested_at,
        },
    )


async def merge_location(code: str) -> str:
    lid = location_id(code)
    await db.write("MERGE (l:Location {id:$id}) ON CREATE SET l.code=$code, l.name=$code, l.kind=$kind", {"id": lid, "code": code, "kind": "region" if "-" in code else "country"})
    return lid


async def merge_rel(
    src: str,
    rel: str,
    dst: str,
    props: dict,
    key_props: dict | None = None,
    *,
    retrievals: list[dict] | None = None,
) -> None:
    props = _with_retrieval_truth({k: v for k, v in props.items() if v is not None}, retrievals)
    props.setdefault("retrieval_mode", _seed_retrieval_mode)
    retrieved_at = props.pop("retrieved_at", None) or now_iso()
    ingested_at = now_iso()
    key = key_props or {}
    key_clause = (" {" + ", ".join(f"{k}: $key.{k}" for k in key) + "}") if key else ""
    await db.write(
        f"MATCH (a {{id:$a}}), (b {{id:$b}}) MERGE (a)-[r:{rel}{key_clause}]->(b) "
        "ON CREATE SET r.id=$rid, r.retrieved_at=$retrieved, r.first_ingested_at=$ingested "
        "SET r += $p, r.retrieved_at=coalesce(r.retrieved_at,$retrieved), "
        "r.latest_retrieved_at=$retrieved, "
        "r.first_ingested_at=coalesce(r.first_ingested_at,$ingested), "
        "r.last_ingested_at=$ingested",
        {
            "a": src,
            "b": dst,
            "p": props,
            "rid": edge_id(),
            "key": key,
            "retrieved": retrieved_at,
            "ingested": ingested_at,
        },
    )


async def merge_artifact(
    aid: str,
    props: dict,
    about: str,
    *,
    retrievals: list[dict] | None = None,
) -> None:
    props = _with_retrieval_truth({k: v for k, v in props.items() if v is not None}, retrievals)
    props.setdefault("retrieval_mode", _seed_retrieval_mode)
    retrieved_at = props.get("retrieved_at") or now_iso()
    props.setdefault("retrieved_at", retrieved_at)
    ingested_at = now_iso()
    source_key = {"USAspending": "usaspending", "GDELT": "gdelt", "GLEIF": "gleif", "LittleSis": "littlesis",
                  "SEC EDGAR": "edgar", "OFAC SDN": "ofac", "OpenCorporates": "opencorporates",
                  "SAM.gov Exclusions (public extract)": "sam_exclusions"}.get(props.get("source"))
    if source_key:
        for key, value in source_metadata(source_key).items():
            props.setdefault(key, value)
        props.setdefault("source_status", "unknown")
        props.setdefault("simulated", False)
    latest = {
        "retrieval_status": props.get("retrieval_status") or props.get("source_status") or "unknown",
        "retrieval_mode": props.get("retrieval_mode"),
        "cache": bool(props.get("cache")),
        "fallback": bool(props.get("fallback")),
        "cache_age_s": props.get("cache_age_s"),
    }
    await db.write(
        "MERGE (a:Artifact {id:$id}) "
        "ON CREATE SET a += $p, a.retrieved_at=$retrieved, a.first_ingested_at=$ingested "
        "SET a.retrieved_at=coalesce(a.retrieved_at,$retrieved), "
        "a.latest_retrieved_at=$retrieved, a.latest_retrieval_status=$latest.retrieval_status, "
        "a.latest_retrieval_mode=$latest.retrieval_mode, a.latest_cache=$latest.cache, "
        "a.latest_fallback=$latest.fallback, a.latest_cache_age_s=$latest.cache_age_s, "
        "a.last_ingested_at=$ingested "
        "WITH a MATCH (e {id:$e}) MERGE (a)-[r:ABOUT]->(e) ON CREATE SET r.id=$rid",
        {"id": aid, "p": props, "latest": latest, "retrieved": retrieved_at,
         "ingested": ingested_at, "e": about, "rid": edge_id()},
    )


async def merge_supply_claim(
    cid: str,
    aid: str,
    supplier_id: str,
    consumer_id: str,
    sole_source: bool,
    source_url: str,
    retrieved_at: str,
    source_status: str,
    retrieval_mode: str,
) -> None:
    """Persist the reviewable award -> claim chain behind a supply determination."""
    ingested_at = now_iso()
    await db.write(
        """
        MERGE (c:Claim {id:$cid})
        ON CREATE SET c.predicate='supply_sole_source', c.subject_id=$supplier,
                      c.object_id=$consumer, c.object_value=$sole_source,
                      c.source='USAspending', c.method='connector',
                      c.confidence=0.95, c.status='committed',
                      c.retrieved_at=$retrieved_at, c.first_ingested_at=$ingested_at,
                      c.source_url=$source_url, c.simulated=false
        SET c.latest_retrieved_at=$retrieved_at, c.last_ingested_at=$ingested_at,
            c.source_status=$source_status, c.retrieval_mode=$retrieval_mode
        WITH c
        MATCH (supplier:Entity {id:$supplier}), (consumer:Entity {id:$consumer}),
              (a:Artifact {id:$aid})
        MERGE (c)-[asserts:ASSERTS]->(supplier)
          ON CREATE SET asserts.id=$asserts_id
        MERGE (c)-[targets:TARGETS]->(consumer)
          ON CREATE SET targets.id=$targets_id
        MERGE (a)-[e:EVIDENCES]->(c)
          ON CREATE SET e.id=$evidence_id, e.source='USAspending',
                        e.method='connector', e.retrieved_at=$retrieved_at,
                        e.first_ingested_at=$ingested_at,
                        e.confidence=0.95, e.simulated=false
        SET e.latest_retrieved_at=$retrieved_at, e.last_ingested_at=$ingested_at,
            e.source_status=$source_status, e.retrieval_mode=$retrieval_mode
        """,
        {
            "cid": cid, "aid": aid, "supplier": supplier_id, "consumer": consumer_id,
            "sole_source": sole_source, "source_url": source_url,
            "retrieved_at": retrieved_at, "source_status": source_status,
            "retrieval_mode": retrieval_mode, "ingested_at": ingested_at,
            "asserts_id": edge_id(), "targets_id": edge_id(), "evidence_id": edge_id(),
        },
    )


def _country(loc: dict | None) -> str | None:
    if not loc:
        return None
    cc = (loc.get("country_code") or "").upper()
    if cc in ("USA", "US"):
        return f"US-{loc['state_code']}" if loc.get("state_code") else "US"
    return cc[:2] if len(cc) == 3 and cc.isalpha() else (cc or None)


async def seed_program(keywords: list[str], root_name: str, *, since: str, until: str, max_primes: int, max_subs: int, agency: str) -> dict:
    root_id = entity_id(name=root_name)
    await merge_entity(root_id, {"name": root_name, "kind": "program", "source": "seed", "method": "seed", "confidence": 1.0, "keywords": keywords})
    log(f"root {root_name} ({root_id})")

    # ---- primes ---------------------------------------------------------------
    by_recipient: dict[str, dict] = {}
    page = 1
    while len(by_recipient) < max_primes * 3 and page <= 4:
        trace_start = len(_seed_retrieval_trace or [])
        res = await search_awards(keywords, start=since, end=until, agency=agency, limit=100, page=page)
        page_retrievals = list((_seed_retrieval_trace or [])[trace_start:])
        rows = res.get("results", [])
        for a in rows:
            rid = a.get("recipient_id")
            if not rid:
                continue
            slot = by_recipient.setdefault(
                rid,
                {"awards": [], "total": 0.0, "name": a.get("Recipient Name"), "retrievals": []},
            )
            a["_retrievals"] = page_retrievals
            slot["awards"].append(a)
            slot["retrievals"].extend(page_retrievals)
            slot["total"] += float(a.get("Award Amount") or 0)
        if not res.get("page_metadata", {}).get("hasNext"):
            break
        page += 1
    ranked = sorted(by_recipient.items(), key=lambda kv: -kv[1]["total"])[:max_primes]
    log(f"{len(by_recipient)} prime recipients found; keeping top {len(ranked)}")

    prime_ids: dict[str, str] = {}  # recipient_id → entity id
    for rid, slot in ranked:
        trace_start = len(_seed_retrieval_trace or [])
        rec = await recipient(rid)
        rec_retrievals = list((_seed_retrieval_trace or [])[trace_start:])
        prime_retrievals = [*slot["retrievals"], *rec_retrievals]
        uei = rec.get("uei")
        eid = entity_id(uei=uei, name=rec.get("name") or slot["name"])
        loc = _country(rec.get("location"))
        await merge_entity(eid, {"name": rec.get("name") or slot["name"], "kind": "organization", "uei": uei, "duns": rec.get("duns"),
                                 "aliases": rec.get("alternate_names") or [], "aliases_norm": [normalize_name(x) for x in rec.get("alternate_names") or []],
                                 "business_types": rec.get("business_types") or [], "source_url": recipient_url(rid), **PROV},
                           retrievals=prime_retrievals)
        if loc:
            await merge_rel(eid, "OPERATES_IN", await merge_location(loc),
                            {**PROV, "source_url": recipient_url(rid), "detail": "recipient address"},
                            retrievals=prime_retrievals)
        prime_ids[rid] = eid
        # top awards → detail for competition + PSC/NAICS
        top = sorted(slot["awards"], key=lambda a: -float(a.get("Award Amount") or 0))[:3]
        psc, naics = None, None
        determinations: list[dict] = []
        for a in top:
            gid = a.get("generated_internal_id")
            if not gid:
                continue
            detail_trace_start = len(_seed_retrieval_trace or [])
            try:
                det = await award_detail(gid)
            except Exception:
                det = {}
            detail_retrievals = list((_seed_retrieval_trace or [])[detail_trace_start:])
            award_retrievals = [*a.get("_retrievals", []), *detail_retrievals]
            prime_retrievals.extend(detail_retrievals)
            ltx = det.get("latest_transaction_contract_data") or {}
            psc = psc or ltx.get("product_or_service_code")
            naics = naics or ltx.get("naics")
            s, w = is_sole_source(det) if det else (None, None)
            award_source_url = award_url(gid)
            award_artifact_id = artifact_id(award_source_url)
            retrieval_truth = _with_retrieval_truth(PROV, award_retrievals)
            source_retrieved_at = retrieval_truth.get("retrieved_at")
            if det and s is not None and source_retrieved_at:
                determinations.append({
                    "award": a, "sole_source": s, "why": w, "url": award_source_url,
                    "artifact_id": award_artifact_id, "retrieved_at": source_retrieved_at,
                    "source_status": retrieval_truth["source_status"],
                    "retrieval_mode": retrieval_truth["retrieval_mode"],
                    "retrievals": award_retrievals,
                })
            await merge_artifact(award_artifact_id, {"kind": "award", "title": f"{a.get('Award ID')} — {(a.get('Description') or '')[:140]}", "url": award_source_url,
                                                                 "source": "USAspending", "published_at": a.get("Start Date"), "amount": a.get("Award Amount"),
                                                                 "agency": a.get("Awarding Sub Agency"), "award_id": a.get("Award ID"), "psc": psc, "naics": naics,
                                                                  "competition": (ltx.get("extent_competed_description") or None)}, eid,
                                 retrievals=award_retrievals)
            pop = _country(det.get("place_of_performance")) if det else None
            if pop and pop != loc:
                await merge_rel(eid, "OPERATES_IN", await merge_location(pop),
                                {**PROV, "source_url": award_url(gid), "detail": "place of performance"},
                                retrievals=award_retrievals)
        cat = psc_category(psc)
        if cat:
            await merge_rel(eid, "PROVIDES", cat, {**PROV, "confidence": 0.7, "detail": f"PSC {psc}"},
                            retrievals=prime_retrievals)
        determination = next((d for d in determinations if d["sole_source"]), None)
        if determination is None and determinations:
            determination = determinations[0]
        supply_claim_id = None
        if determination:
            supply_claim_id = stable_id(
                "clm", "supply_sole_source", eid, root_id,
                determination["artifact_id"], str(bool(determination["sole_source"])),
            )
            await merge_supply_claim(
                supply_claim_id, determination["artifact_id"], eid, root_id,
                bool(determination["sole_source"]), determination["url"],
                determination["retrieved_at"], determination["source_status"],
                determination["retrieval_mode"],
            )
        await merge_rel(
            eid,
            "SUPPLIES",
            root_id,
            {
                "tier": 1,
                "sole_source": bool(determination["sole_source"]) if determination else None,
                "competition": determination["why"] if determination else None,
                "amount": round(slot["total"], 2),
                "award_count": len(slot["awards"]),
                "contract_ref": determination["award"].get("Award ID") if determination else None,
                "psc": psc,
                "naics": naics,
                "status": "committed",
                "claim_id": supply_claim_id,
                **PROV,
                "source_url": determination["url"] if determination else None,
            },
            retrievals=determination["retrievals"] if determination else prime_retrievals,
        )
        # USAspending parent recipient → OWNS
        puei = rec.get("parent_uei")
        if puei and puei != uei and rec.get("parent_name"):
            pid = entity_id(uei=puei)
            await merge_entity(pid, {"name": rec["parent_name"], "kind": "organization", "uei": puei, "source_url": recipient_url(rec["parent_id"]) if rec.get("parent_id") else None, **PROV},
                               retrievals=prime_retrievals)
            await merge_rel(pid, "OWNS", eid, {**PROV, "detail": "USAspending parent recipient"},
                            retrievals=prime_retrievals)
    log(f"{len(prime_ids)} tier-1 suppliers written")

    # ---- subawards ------------------------------------------------------------
    subs_seen: dict[str, dict] = {}
    page = 1
    while len(subs_seen) < max_subs and page <= 5:
        trace_start = len(_seed_retrieval_trace or [])
        res = await search_awards(keywords, start=since, end=until, agency=None, limit=100, page=page, subawards=True)
        page_retrievals = list((_seed_retrieval_trace or [])[trace_start:])
        for s in res.get("results", []):
            key = (s.get("Sub-Awardee Name") or "").strip().upper()
            if not key:
                continue
            slot = subs_seen.setdefault(key, {"rows": [], "total": 0.0, "retrievals": []})
            s["_retrievals"] = page_retrievals
            slot["rows"].append(s)
            slot["retrievals"].extend(page_retrievals)
            slot["total"] += float(s.get("Sub-Award Amount") or 0)
        if not res.get("page_metadata", {}).get("hasNext"):
            break
        page += 1
    ranked_subs = sorted(subs_seen.items(), key=lambda kv: -kv[1]["total"])[:max_subs]
    log(f"{len(subs_seen)} sub-awardees found; keeping top {len(ranked_subs)}")

    n_sub = 0
    for name_key, slot in ranked_subs:
        rows = slot["rows"]
        r0 = rows[0]
        sub_rid = r0.get("sub_award_recipient_id")
        uei = None
        display = r0.get("Sub-Awardee Name")
        loc = None
        src_url = f"https://www.usaspending.gov/award/{r0.get('prime_award_generated_internal_id')}"
        sub_retrievals = list(slot["retrievals"])
        if sub_rid:
            trace_start = len(_seed_retrieval_trace or [])
            try:
                rec = await recipient(sub_rid)
                uei, display, loc = rec.get("uei"), rec.get("name") or display, _country(rec.get("location"))
                src_url = recipient_url(sub_rid)
            except Exception:
                pass
            sub_retrievals.extend((_seed_retrieval_trace or [])[trace_start:])
        sid = entity_id(uei=uei, name=display)
        await merge_entity(sid, {"name": display, "kind": "organization", "uei": uei, "source_url": src_url, **PROV, "confidence": 0.9 if uei else 0.75, "method": "connector" if uei else "name_match"},
                           retrievals=sub_retrievals)
        if loc:
            await merge_rel(sid, "OPERATES_IN", await merge_location(loc), {**PROV, "source_url": src_url},
                            retrievals=sub_retrievals)
        # attach to each distinct prime
        primes_for_sub = defaultdict(float)
        for s in rows:
            primes_for_sub[(s.get("prime_award_recipient_id"), s.get("Prime Recipient Name"), s.get("prime_award_generated_internal_id"), s.get("Prime Award ID"))] += float(s.get("Sub-Award Amount") or 0)
        for (prid, pname, pgid, paward), amt in primes_for_sub.items():
            award_retrievals = [
                trace
                for row in rows
                if row.get("prime_award_recipient_id") == prid
                for trace in row.get("_retrievals", [])
            ]
            pid = prime_ids.get(prid)
            if not pid:
                # prime not in the top-N — bring it in at tier 1 so the path to root exists
                trace_start = len(_seed_retrieval_trace or [])
                try:
                    prec = await recipient(prid) if prid else {}
                except Exception:
                    prec = {}
                prime_retrievals = [
                    *award_retrievals,
                    *list((_seed_retrieval_trace or [])[trace_start:]),
                ]
                pid = entity_id(uei=prec.get("uei"), name=prec.get("name") or pname)
                await merge_entity(pid, {"name": prec.get("name") or pname, "kind": "organization", "uei": prec.get("uei"), "source_url": recipient_url(prid) if prid else None, **PROV},
                                   retrievals=prime_retrievals)
                await merge_rel(pid, "SUPPLIES", root_id, {"tier": 1, "sole_source": False, "contract_ref": paward, **PROV, "source_url": award_url(pgid) if pgid else None, "detail": "prime of a reported subaward"},
                                retrievals=prime_retrievals)
                if prid:
                    prime_ids[prid] = pid
            await merge_rel(sid, "SUPPLIES", pid, {"tier": 2, "sole_source": False, "amount": round(amt, 2), "contract_ref": paward, "sub_award_ids": [s.get("Sub-Award ID") for s in rows if s.get("prime_award_recipient_id") == prid][:10],
                                                  "description": (rows[0].get("Sub-Award Description") or "")[:200], **PROV, "source_url": award_url(pgid) if pgid else None},
                            retrievals=award_retrievals)
            for s in rows[:2]:
                if s.get("prime_award_generated_internal_id") == pgid:
                    aid = artifact_id(f"{award_url(pgid)}#{s.get('Sub-Award ID')}")
                    await merge_artifact(aid, {"kind": "award", "title": f"Subaward {s.get('Sub-Award ID')} — {(s.get('Sub-Award Description') or '')[:120]}", "url": award_url(pgid),
                                               "source": "USAspending", "published_at": s.get("Sub-Award Date"), "amount": s.get("Sub-Award Amount"), "award_id": paward}, sid,
                                         retrievals=s.get("_retrievals", []))
        n_sub += 1
    log(f"{n_sub} tier-2 suppliers written")
    return {"root_id": root_id, "root_name": root_name, "primes": len(prime_ids), "subs": n_sub}


async def enrich_with(connector_names: list[str], entity_ids: list[str], *, commit_open: bool) -> None:
    for name in connector_names:
        conn = get_connector(name)
        if not conn:
            continue
        n_facts = n_commit = 0
        for eid in entity_ids:
            rows = await db.read("MATCH (e:Entity {id:$id}) RETURN e{.*} AS e", {"id": eid})
            if not rows:
                continue
            try:
                facts = await conn.enrich(rows[0]["e"], "local")
            except Exception as e:
                await claims.record_connector_error(name, eid, e)
                safe_error = claims.connector_error_metadata(e)["connector_error"]
                log(f"  {name}: {rows[0]['e']['name']}: {safe_error}")
                if type(e).__name__ == "SAMRateLimited":
                    log(f"  {name}: stopping this pass — remaining entities keep their cached results only")
                    break
                continue
            for f in facts:
                cid = await claims.stage(f, source=conn.name, trust=conn.trust)
                st = await claims.decide(cid, trust=conn.trust)
                if st == "staged" and commit_open:
                    st = await claims.commit(cid, note="seed: pre-event build committed from open source")
                n_facts += 1
                n_commit += st == "committed"
        log(f"{name}: {n_facts} facts, {n_commit} committed over {len(entity_ids)} entities")

async def seed_catalog_lineage() -> None:
    """Load deterministic representative retrieval records for the judged catalog path."""
    records = json.loads(CATALOG_FIXTURE.read_text())["records"]
    for raw_record in records:
        record = dict(raw_record)
        cached = json.loads((FIXTURES / record["cache_fixture"]).read_text())
        stamp = cached.get("_ts") or cached.get("retrieved_at")
        if isinstance(stamp, (int, float)):
            stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stamp))
        if not stamp:
            raise ValueError(f"catalog fixture {record['cache_fixture']} has no retrieval timestamp")
        record["retrieved_at"] = stamp
        ingested_at = now_iso()
        meta = source_metadata(record["connector"])
        await db.write(
            "MERGE (r:SourceRecord {id:$id}) "
            "ON CREATE SET r += $meta, r += $record, r.first_ingested_at=$ingested "
            "SET r.last_ingested_at=$ingested",
            {"id": record["id"], "meta": meta, "record": record, "ingested": ingested_at},
        )

async def seed_cached_gdelt() -> bool:
    """Ingest one attributable GKG record so the offline demo has real cached media evidence."""
    record = json.loads((FIXTURES / "gdelt_gkg_20260908160000_92.json").read_text())
    subject = await db.read(
        "MATCH (e:Entity) WHERE toLower(e.name) CONTAINS $name RETURN e.id AS id ORDER BY e.name LIMIT 1",
        {"name": record["matched_entity"].lower()},
    )
    if not subject:
        log(f"GDELT cached record {record['gkg_record_id']}: no {record['matched_entity']} entity; association skipped")
        return False
    entity = subject[0]["id"]
    await merge_artifact(
        artifact_id(record["article_url"]),
        {
            "kind": "news",
            "title": record["title"],
            "url": record["article_url"],
            "source": "GDELT",
            "source_identifier": record["gkg_record_id"],
            "retrieved_at": record["retrieved_at"],
            "source_status": "cached",
            "published_at": record["published_at"],
            "domain": record["domain"],
            "sentiment": record["tone"],
            "gkg_bulk_file": record["bulk_file_url"],
            "gkg_bulk_md5": record["bulk_md5"],
        },
        entity,
    )
    return True
async def scenario(root_id: str) -> None:
    """A clearly-labelled simulated adversarial tie (the brief allows 'simulated or
    historical'). Every node/edge carries simulated=true and a '(simulated)' suffix."""
    S = {"source": "scenario", "method": "simulated", "confidence": 1.0, "simulated": True, "source_url": "https://example.invalid/scenario"}
    # host: a real tier-2 supplier that provides goods, preferring structures/metals
    host = await db.read(
        "MATCH (h:Entity)-[s:SUPPLIES {tier:2}]->(p:Entity) OPTIONAL MATCH (h)-[:PROVIDES]->(c:Category) "
        "WITH h, p, collect(c.id) AS cats ORDER BY (CASE WHEN any(x IN cats WHERE x IN ['cat_structures','cat_metals','cat_aircraft_components']) THEN 0 ELSE 1 END), h.name "
        "RETURN h.id AS id, h.name AS name, p.id AS prime LIMIT 1")
    if not host:
        host = await db.read("MATCH (h:Entity)-[:SUPPLIES {tier:1}]->(:Entity {id:$r}) RETURN h.id AS id, h.name AS name, null AS prime ORDER BY h.name LIMIT 1", {"r": root_id})
    if not host:
        log("scenario: no host supplier found; skipping")
        return
    h = host[0]
    tier = 3 if h["prime"] else 2
    ning = entity_id(cage="7F2K9")
    hk = entity_id(name="Pacific Alloy Holdings (simulated)")
    zj = entity_id(name="Zhejiang Provincial Metals Group (simulated)")
    await merge_entity(ning, {"name": "Ningbo Precision Castings Ltd (simulated)", "kind": "organization", "cage": "7F2K9", "uei": "ZQ4MSIMUL8T1", "registration_status": "Active", **S})
    await merge_entity(hk, {"name": "Pacific Alloy Holdings (simulated)", "kind": "organization", **S})
    await merge_entity(zj, {"name": "Zhejiang Provincial Metals Group (simulated)", "kind": "organization", "state_owned": True, **S})
    for code in ("US-DE", "CN", "HK"):
        await merge_location(code)
    await merge_rel(ning, "INCORPORATED_IN", location_id("US-DE"), {**S, "detail": "Delaware shell; manufactures abroad"})
    await merge_rel(ning, "MANUFACTURES_IN", location_id("CN"), {**S, "detail": "Ningbo plant — the country-of-manufacture question turns on this edge"})
    await merge_rel(ning, "PARENT_SEATED_IN", location_id("CN"), {**S})
    await merge_rel(hk, "INCORPORATED_IN", location_id("HK"), S)
    await merge_rel(zj, "INCORPORATED_IN", location_id("CN"), S)
    await merge_rel(hk, "OWNS", ning, {**S, "pct": 100.0})
    await merge_rel(zj, "OWNS", hk, {**S, "pct": 100.0})
    await merge_rel(zj, "ULTIMATE_PARENT_OF", ning, {**S, "detail": "100% via two intermediaries"})
    await merge_rel(ning, "PROVIDES", "cat_castings", S)
    await merge_rel(ning, "SUPPLIES", h["id"], {**S, "tier": tier, "sole_source": True, "psc": "1615", "contract_ref": "SIM-PO-0417", "detail": "sole-source investment castings"})
    # people: a former director of the host now on Ningbo's board; a director sitting on two real supplier boards
    p1 = person_id("S. Reinhardt (simulated)", "scenario")
    await db.write("MERGE (p:Person {id:$id}) SET p += $p", {"id": p1, "p": {"name": "S. Reinhardt (simulated)", "name_norm": "s reinhardt simulated", **S}})
    await merge_rel(p1, "HELD_ROLE", h["id"], {**S, "title": "Director", "role_type": "board", "from": "2018-02-01", "to": "2022-11-30", "current": False}, {"from": "2018-02-01"})
    await merge_rel(p1, "HELD_ROLE", ning, {**S, "title": "Director", "role_type": "board", "from": "2023-01-15", "current": True}, {"from": "2023-01-15"})
    two = await db.read("MATCH (a:Entity)-[:SUPPLIES]->(:Entity {id:$r}) WHERE a.id <> $h AND coalesce(a.simulated,false)=false RETURN a.id AS id ORDER BY a.name LIMIT 2", {"r": root_id, "h": h["id"]})
    if len(two) == 2:
        p2 = person_id("M. Fairweather (simulated)", "scenario")
        await db.write("MERGE (p:Person {id:$id}) SET p += $p", {"id": p2, "p": {"name": "M. Fairweather (simulated)", "name_norm": "m fairweather simulated", **S}})
        await merge_rel(p2, "HELD_ROLE", two[0]["id"], {**S, "title": "Director", "role_type": "board", "from": "2023-01-01", "current": True}, {"from": "2023-01-01"})
        await merge_rel(p2, "HELD_ROLE", two[1]["id"], {**S, "title": "Chair", "role_type": "board", "from": "2021-06-01", "current": True}, {"from": "2021-06-01"})
    # screens for the simulated entity: clear (it is the opacity, not a listing, that matters)
    for pred, src in (("sanctions_screen", "OFAC"), ("exclusion_screen", "SAM.gov")):
        await db.write("MERGE (c:Claim {id:$cid}) SET c += $p WITH c MATCH (e:Entity {id:$e}) MERGE (c)-[r:ASSERTS]->(e) ON CREATE SET r.id=$rid",
                       {"cid": f"clm_sim_{pred}", "e": ning, "rid": edge_id(), "p": {"predicate": pred, "subject_id": ning, "object_value": "clear", "source": src, "trust": "authoritative", "method": "simulated", "confidence": 0.9, "status": "committed", "retrieved_at": now_iso(), "detail": "simulated screen result: clear", "simulated": True}})
    await db.write("MATCH (e:Entity {id:$id}) SET e.flagged = true, e.flag_reason = 'foreign ultimate parent via two intermediaries (simulated scenario)'", {"id": ning})
    log(f"scenario: Ningbo Precision Castings (simulated) attached at tier {tier} under {h['name']}")


async def stats() -> dict:
    n = await db.read("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS c ORDER BY c DESC")
    r = await db.read("MATCH ()-[x]->() RETURN type(x) AS t, count(*) AS c ORDER BY c DESC")
    return {"nodes": {x["l"]: x["c"] for x in n}, "rels": {x["t"]: x["c"] for x in r}}


async def mark_seed_started(args) -> None:
    """Invalidate any prior completion stamp before reset or replay begins."""
    await db.write(
        "MERGE (m:SeedMetadata {id:'primary'}) "
        "SET m.version=$version, m.status='running', m.started_at=$started, "
        "m.completed_at=null, m.offline=$offline, m.scenario=$scenario",
        {
            "version": SEED_VERSION,
            "started": now_iso(),
            "offline": args.offline,
            "scenario": args.scenario,
        },
    )


async def main_async(args) -> None:
    global _seed_retrieval_mode, _seed_retrieval_trace
    bootstrap = bool(getattr(args, "bootstrap", False))
    if bootstrap and args.offline:
        raise ValueError("--bootstrap cannot use offline fixtures")
    _seed_retrieval_mode = "offline_fixture" if args.offline else "operational_live"
    # A production bootstrap uses only the runtime cache. It must never read or
    # mutate the committed fixture directory.
    set_cache_dir(FIXTURES if args.offline else settings.data_dir / "http_cache",
                  read_only=args.offline, fixture_store=args.offline)
    await ensure_schema()
    await mark_seed_started(args)
    if bootstrap:
        # Rehearsal-only overlays must never survive into the operational view.
        await db.write("MATCH ()-[r]->() WHERE coalesce(r.simulated,false)=true DELETE r")
        await db.write("MATCH (n) WHERE coalesce(n.simulated,false)=true DETACH DELETE n")
    if args.reset:
        await reset_graph()
    if not bootstrap:
        await seed_catalog_lineage()
    # Retain the trace while records are merged, so runtime-cache results carry
    # their real cache/live/fallback state and original response timestamp.
    try:
        with retrieval_context(_seed_retrieval_mode) as retrievals:
            _seed_retrieval_trace = retrievals
            info = await seed_program(args.keyword, args.root_name, since=args.since, until=args.until, max_primes=args.primes, max_subs=args.subs, agency=args.agency)
    finally:
        _seed_retrieval_trace = None
    if not bootstrap:
        await seed_cached_gdelt()
    # enrichment: authoritative connectors over every supplier; people/EDGAR over the biggest
    all_ids = [r["id"] for r in await db.read("MATCH (e:Entity) WHERE e.kind='organization' AND coalesce(e.simulated,false)=false RETURN e.id AS id")]
    top_ids = [r["id"] for r in await db.read(
        "MATCH (e:Entity)-[s:SUPPLIES]->() WHERE coalesce(e.simulated,false)=false RETURN e.id AS id, sum(coalesce(s.amount,0)) AS amt ORDER BY amt DESC LIMIT $n", {"n": args.people})]
    if not args.skip_enrich:
        await enrich_with(["gleif"], all_ids, commit_open=False)
        await enrich_with(["ofac"], all_ids, commit_open=False)
        await enrich_with(["sam_exclusions"], all_ids, commit_open=False)
        if (await get_connector("sam").status("local")).get("connected"):
            await enrich_with(["sam"], all_ids, commit_open=False)
        else:
            log("sam: no SAM.gov key in vault — registration/exclusion screen skipped")
        # a parent brought in by GLEIF deserves a jurisdiction + screen too
        parents = [r["id"] for r in await db.read("MATCH (p:Entity)-[:OWNS|ULTIMATE_PARENT_OF]->(:Entity) WHERE NOT (p)-[:SUPPLIES]->() AND coalesce(p.simulated,false)=false RETURN DISTINCT p.id AS id")]
        await enrich_with(["gleif", "ofac", "sam_exclusions"], parents, commit_open=False)
        await enrich_with(["littlesis"], top_ids + parents[:10], commit_open=True)
        await enrich_with(["edgar"], top_ids + parents[:10], commit_open=False)
    if args.scenario:
        if bootstrap:
            raise ValueError("--bootstrap cannot add a simulation scenario")
        await scenario(info["root_id"])
    seed_status = "complete" if info["primes"] > 0 and info["subs"] > 0 else "incomplete"
    await db.write(
        "MERGE (m:SeedMetadata {id:'primary'}) "
        "SET m.version=$version, m.status=$status, m.completed_at=$completed, "
        "m.offline=$offline, m.scenario=$scenario, m.root_id=$root_id, "
        "m.primes=$primes, m.subs=$subs",
        {"version": SEED_VERSION, "completed": now_iso(), "offline": args.offline,
         "scenario": args.scenario, "root_id": info["root_id"], "status": seed_status,
         "primes": info["primes"], "subs": info["subs"]},
    )
    st = await stats()
    log(f"done: {json.dumps(st)}")
    await db.close_driver()


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed a real program graph")
    ap.add_argument("--keyword", action="append", default=None, help="USAspending keyword(s); default V-22")
    ap.add_argument("--root-name", default="V-22 Osprey Program (PMA-275)")
    ap.add_argument("--agency", default="Department of Defense")
    ap.add_argument("--since", default="2019-10-01")
    ap.add_argument("--until", default="2026-09-30")
    ap.add_argument("--primes", type=int, default=20)
    ap.add_argument("--subs", type=int, default=60)
    ap.add_argument("--people", type=int, default=10, help="how many top suppliers get the people layer")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--offline", action="store_true", help="only read from committed fixtures")
    ap.add_argument("--scenario", action="store_true", help="add the simulated adversarial-tie overlay")
    ap.add_argument("--skip-enrich", action="store_true")
    ap.add_argument("--bootstrap", action="store_true",
                    help="live-only production recovery; never imports or writes committed fixtures")
    args = ap.parse_args()
    if not args.keyword:
        args.keyword = ["V-22"]
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
