"""Pre-seed one real program's graph so the live demo runs against warm data.

    python -m illuminate.seed.seed --program "V-22" --scenario
    python -m illuminate.seed.seed --offline        # rebuild from committed fixtures

Sources: USAspending (primes, subawards, recipients, competition), GLEIF (LEI,
jurisdiction, parents), OFAC SDN (sanctions screen), LittleSis (people, their other
seats, ownership, memberships, lobbying, transactions), EDGAR (listed parents). Every
HTTP response is cached under seed/fixtures so the graph rebuilds offline; see
seed/record.py to add fixtures when a connector grows. --scenario adds a clearly-labelled simulated adversarial tie,
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
from ..connectors.http import set_cache_dir
from ..connectors.registry import source_metadata
from ..connectors.usaspending import award_detail, award_url, is_sole_source, psc_category, recipient, recipient_url, search_awards
from ..enrichment import claims
from ..ids import edge_id, entity_id, location_id, normalize_name, person_id, artifact_id
from ..schema import ensure_schema

FIXTURES = Path(__file__).resolve().parent / "fixtures"
CATALOG_FIXTURE = FIXTURES / "catalog_lineage.json"
PROV = {"source": "USAspending", "method": "connector", "confidence": 0.95}
SEED_VERSION = "uc7-fixtures-v1"


def log(msg: str) -> None:
    print(f"[seed {time.strftime('%H:%M:%S')}] {msg}", flush=True)


async def reset_graph() -> None:
    await db.write("MATCH (n) WHERE NOT n:Category DETACH DELETE n")
    log("graph reset (categories kept)")


async def merge_entity(eid: str, props: dict) -> None:
    props = {k: v for k, v in props.items() if v is not None}
    retrieved_at = props.pop("retrieved_at", None) or now_iso()
    ingested_at = now_iso()
    await db.write(
        "MERGE (e:Entity {id:$id}) "
        "ON CREATE SET e.retrieved_at=$retrieved, e.first_ingested_at=$ingested "
        "SET e += $p, e.retrieved_at=coalesce(e.retrieved_at,$retrieved), "
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


async def merge_rel(src: str, rel: str, dst: str, props: dict, key_props: dict | None = None) -> None:
    props = {k: v for k, v in props.items() if v is not None}
    retrieved_at = props.pop("retrieved_at", None) or now_iso()
    ingested_at = now_iso()
    key = key_props or {}
    key_clause = (" {" + ", ".join(f"{k}: $key.{k}" for k in key) + "}") if key else ""
    await db.write(
        f"MATCH (a {{id:$a}}), (b {{id:$b}}) MERGE (a)-[r:{rel}{key_clause}]->(b) "
        "ON CREATE SET r.id=$rid, r.retrieved_at=$retrieved, r.first_ingested_at=$ingested "
        "SET r += $p, r.retrieved_at=coalesce(r.retrieved_at,$retrieved), "
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


async def merge_artifact(aid: str, props: dict, about: str) -> None:
    props = {k: v for k, v in props.items() if v is not None}
    props.setdefault("retrieved_at", now_iso())
    ingested_at = now_iso()
    source_key = {"USAspending": "usaspending", "GDELT": "gdelt", "GLEIF": "gleif", "LittleSis": "littlesis",
                  "SEC EDGAR": "edgar", "OFAC SDN": "ofac", "OpenCorporates": "opencorporates",
                  "SAM.gov Exclusions (public extract)": "sam_exclusions"}.get(props.get("source"))
    if source_key:
        for key, value in source_metadata(source_key).items():
            props.setdefault(key, value)
        props.setdefault("source_status", "retrieved")
        props.setdefault("simulated", False)
    await db.write(
        "MERGE (a:Artifact {id:$id}) "
        "ON CREATE SET a += $p, a.first_ingested_at=$ingested "
        "SET a.last_ingested_at=$ingested "
        "WITH a MATCH (e {id:$e}) MERGE (a)-[r:ABOUT]->(e) ON CREATE SET r.id=$rid",
        {"id": aid, "p": props, "ingested": ingested_at, "e": about, "rid": edge_id()},
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
        res = await search_awards(keywords, start=since, end=until, agency=agency, limit=100, page=page)
        rows = res.get("results", [])
        for a in rows:
            rid = a.get("recipient_id")
            if not rid:
                continue
            slot = by_recipient.setdefault(rid, {"awards": [], "total": 0.0, "name": a.get("Recipient Name")})
            slot["awards"].append(a)
            slot["total"] += float(a.get("Award Amount") or 0)
        if not res.get("page_metadata", {}).get("hasNext"):
            break
        page += 1
    ranked = sorted(by_recipient.items(), key=lambda kv: -kv[1]["total"])[:max_primes]
    log(f"{len(by_recipient)} prime recipients found; keeping top {len(ranked)}")

    prime_ids: dict[str, str] = {}  # recipient_id → entity id
    for rid, slot in ranked:
        # USAspending serves some recipient profiles as a 502 that never resolves (and offline,
        # one may simply not be recorded). The award rows still name the recipient, so it is
        # kept on what they carry, the way the sub-awardee pass already does, rather than
        # letting one broken profile abort the whole seed.
        try:
            rec = await recipient(rid)
        except Exception as e:
            log(f"recipient profile unavailable for {slot['name']} ({rid}): {type(e).__name__}: {e}; keeping the award-row name")
            rec = {}
        uei = rec.get("uei")
        eid = entity_id(uei=uei, name=rec.get("name") or slot["name"])
        loc = _country(rec.get("location"))
        await merge_entity(eid, {"name": rec.get("name") or slot["name"], "kind": "organization", "uei": uei, "duns": rec.get("duns"),
                                 "aliases": rec.get("alternate_names") or [], "aliases_norm": [normalize_name(x) for x in rec.get("alternate_names") or []],
                                 "business_types": rec.get("business_types") or [], "source_url": recipient_url(rid), **PROV,
                                 **({} if rec else {"confidence": 0.75, "method": "name_match"})})
        if loc:
            await merge_rel(eid, "OPERATES_IN", await merge_location(loc), {**PROV, "source_url": recipient_url(rid), "detail": "recipient address"})
        prime_ids[rid] = eid
        # top awards → detail for competition + PSC/NAICS
        top = sorted(slot["awards"], key=lambda a: -float(a.get("Award Amount") or 0))[:3]
        sole_any, psc, naics, why = False, None, None, None
        for a in top:
            gid = a.get("generated_internal_id")
            if not gid:
                continue
            try:
                det = await award_detail(gid)
            except Exception:
                det = {}
            ltx = det.get("latest_transaction_contract_data") or {}
            psc = psc or ltx.get("product_or_service_code")
            naics = naics or ltx.get("naics")
            s, w = is_sole_source(det) if det else (False, None)
            sole_any, why = sole_any or s, why or w
            await merge_artifact(artifact_id(award_url(gid)), {"kind": "award", "title": f"{a.get('Award ID')} — {(a.get('Description') or '')[:140]}", "url": award_url(gid),
                                                                 "source": "USAspending", "published_at": a.get("Start Date"), "amount": a.get("Award Amount"),
                                                                 "agency": a.get("Awarding Sub Agency"), "award_id": a.get("Award ID"), "psc": psc, "naics": naics,
                                                                 "competition": (ltx.get("extent_competed_description") or None)}, eid)
            pop = _country(det.get("place_of_performance")) if det else None
            if pop and pop != loc:
                await merge_rel(eid, "OPERATES_IN", await merge_location(pop), {**PROV, "source_url": award_url(gid), "detail": "place of performance"})
        cat = psc_category(psc)
        if cat:
            await merge_rel(eid, "PROVIDES", cat, {**PROV, "confidence": 0.7, "detail": f"PSC {psc}"})
        await merge_rel(eid, "SUPPLIES", root_id, {"tier": 1, "sole_source": bool(sole_any), "competition": why, "amount": round(slot["total"], 2), "award_count": len(slot["awards"]),
                                                  "contract_ref": top[0].get("Award ID") if top else None, "psc": psc, "naics": naics, **PROV,
                                                  "source_url": award_url(top[0]["generated_internal_id"]) if top and top[0].get("generated_internal_id") else None})
        # USAspending parent recipient → OWNS
        puei = rec.get("parent_uei")
        if puei and puei != uei and rec.get("parent_name"):
            pid = entity_id(uei=puei)
            await merge_entity(pid, {"name": rec["parent_name"], "kind": "organization", "uei": puei, "source_url": recipient_url(rec["parent_id"]) if rec.get("parent_id") else None, **PROV})
            await merge_rel(pid, "OWNS", eid, {**PROV, "detail": "USAspending parent recipient"})
    log(f"{len(prime_ids)} tier-1 suppliers written")

    # ---- subawards ------------------------------------------------------------
    subs_seen: dict[str, dict] = {}
    page = 1
    while len(subs_seen) < max_subs and page <= 5:
        res = await search_awards(keywords, start=since, end=until, agency=None, limit=100, page=page, subawards=True)
        for s in res.get("results", []):
            key = (s.get("Sub-Awardee Name") or "").strip().upper()
            if not key:
                continue
            slot = subs_seen.setdefault(key, {"rows": [], "total": 0.0})
            slot["rows"].append(s)
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
        if sub_rid:
            try:
                rec = await recipient(sub_rid)
                uei, display, loc = rec.get("uei"), rec.get("name") or display, _country(rec.get("location"))
                src_url = recipient_url(sub_rid)
            except Exception:
                pass
        sid = entity_id(uei=uei, name=display)
        await merge_entity(sid, {"name": display, "kind": "organization", "uei": uei, "source_url": src_url, **PROV, "confidence": 0.9 if uei else 0.75, "method": "connector" if uei else "name_match"})
        if loc:
            await merge_rel(sid, "OPERATES_IN", await merge_location(loc), {**PROV, "source_url": src_url})
        # attach to each distinct prime
        primes_for_sub = defaultdict(float)
        for s in rows:
            primes_for_sub[(s.get("prime_award_recipient_id"), s.get("Prime Recipient Name"), s.get("prime_award_generated_internal_id"), s.get("Prime Award ID"))] += float(s.get("Sub-Award Amount") or 0)
        for (prid, pname, pgid, paward), amt in primes_for_sub.items():
            pid = prime_ids.get(prid)
            if not pid:
                # prime not in the top-N — bring it in at tier 1 so the path to root exists
                try:
                    prec = await recipient(prid) if prid else {}
                except Exception:
                    prec = {}
                pid = entity_id(uei=prec.get("uei"), name=prec.get("name") or pname)
                await merge_entity(pid, {"name": prec.get("name") or pname, "kind": "organization", "uei": prec.get("uei"), "source_url": recipient_url(prid) if prid else None, **PROV})
                await merge_rel(pid, "SUPPLIES", root_id, {"tier": 1, "sole_source": False, "contract_ref": paward, **PROV, "source_url": award_url(pgid) if pgid else None, "detail": "prime of a reported subaward"})
                if prid:
                    prime_ids[prid] = pid
            await merge_rel(sid, "SUPPLIES", pid, {"tier": 2, "sole_source": False, "amount": round(amt, 2), "contract_ref": paward, "sub_award_ids": [s.get("Sub-Award ID") for s in rows if s.get("prime_award_recipient_id") == prid][:10],
                                                  "description": (rows[0].get("Sub-Award Description") or "")[:200], **PROV, "source_url": award_url(pgid) if pgid else None})
            for s in rows[:2]:
                if s.get("prime_award_generated_internal_id") == pgid:
                    aid = artifact_id(f"{award_url(pgid)}#{s.get('Sub-Award ID')}")
                    await merge_artifact(aid, {"kind": "award", "title": f"Subaward {s.get('Sub-Award ID')} — {(s.get('Sub-Award Description') or '')[:120]}", "url": award_url(pgid),
                                               "source": "USAspending", "published_at": s.get("Sub-Award Date"), "amount": s.get("Sub-Award Amount"), "award_id": paward}, sid)
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


async def main_async(args) -> None:
    set_cache_dir(FIXTURES, read_only=args.offline)
    await ensure_schema()
    if args.reset:
        await reset_graph()
    await seed_catalog_lineage()
    info = await seed_program(args.keyword, args.root_name, since=args.since, until=args.until, max_primes=args.primes, max_subs=args.subs, agency=args.agency)
    await seed_cached_gdelt()
    # enrichment: authoritative connectors over every supplier; people/EDGAR over the biggest
    all_ids = [r["id"] for r in await db.read("MATCH (e:Entity) WHERE e.kind='organization' AND coalesce(e.simulated,false)=false RETURN e.id AS id")]
    top_ids = [r["id"] for r in await db.read(
        "MATCH (e:Entity)-[s:SUPPLIES]->() WHERE coalesce(e.simulated,false)=false RETURN e.id AS id, sum(coalesce(s.amount,0)) AS amt ORDER BY amt DESC, id LIMIT $n", {"n": args.people})]
    if not args.skip_enrich:
        await enrich_with(["gleif"], all_ids, commit_open=False)
        await enrich_with(["ofac"], all_ids, commit_open=False)
        await enrich_with(["sam_exclusions"], all_ids, commit_open=False)
        if (await get_connector("sam").status("local")).get("connected"):
            await enrich_with(["sam"], all_ids, commit_open=False)
        else:
            log("sam: no SAM.gov key in vault — registration/exclusion screen skipped")
        # a parent brought in by GLEIF deserves a jurisdiction + screen too. Ordered by what its
        # subsidiaries supply so the ten that also get the people layer are the same every run —
        # an unordered pick chose different parents offline than the fixtures were recorded for.
        parents = [r["id"] for r in await db.read(
            "MATCH (p:Entity)-[:OWNS|ULTIMATE_PARENT_OF]->(c:Entity) WHERE NOT (p)-[:SUPPLIES]->() AND coalesce(p.simulated,false)=false "
            "OPTIONAL MATCH (c)-[s:SUPPLIES]->() RETURN p.id AS id, sum(coalesce(s.amount,0)) AS amt ORDER BY amt DESC, id")]
        await enrich_with(["gleif", "ofac", "sam_exclusions"], parents, commit_open=False)
        await enrich_with(["littlesis"], top_ids + parents[:10], commit_open=True)
        await enrich_with(["edgar"], top_ids + parents[:10], commit_open=False)
    if args.scenario:
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
    args = ap.parse_args()
    if not args.keyword:
        args.keyword = ["V-22"]
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
