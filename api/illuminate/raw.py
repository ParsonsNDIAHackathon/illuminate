"""Find the raw source payload behind an Artifact.

Artifact nodes carry the human-facing page URL plus a few extracted fields; the JSON the
connector actually received is cached on disk as {_ts, url, body} — under seed/fixtures for
the offline seed and data/http_cache for live enrichment. Two strategies, in order:

1. Derive the API request(s) that produced the artifact from its page URL (award → awards
   detail, LEI record → lei-records, LittleSis org → entities, EDGAR filing → submissions)
   and look the cache key up directly.
2. Fall back to scanning every cached file for a distinctive token (award id, LEI, CIK,
   accession number …) and return the sub-record that contains it. The caches total a few
   megabytes, so this is cheap; results are memoised per artifact id.
"""
from __future__ import annotations

import functools
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .connectors.http import _key, cache_dir

FIXTURES = Path(__file__).resolve().parent / "seed" / "fixtures"
USA = "https://api.usaspending.gov/api/v2"
MAX_HITS = 3
SOURCE_HOST = {"USAspending": "usaspending.gov", "GLEIF": "gleif.org", "LittleSis": "littlesis.org", "EDGAR": "sec.gov",
               "SAM.gov": "sam.gov", "GDELT": "gdeltproject.org", "OpenCorporates": "opencorporates.com", "Finnhub": "finnhub.io"}


def _dirs() -> list[Path]:
    return [d for d in (cache_dir(), FIXTURES) if d.exists()]


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if ts else None


def _load(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text())
    except Exception:
        return None
    if not isinstance(doc, dict) or "body" not in doc:
        return None
    return {"url": doc.get("url"), "retrieved_at": _iso(doc.get("_ts")), "body": doc["body"], "file": path.name}


def _by_url(url: str) -> dict | None:
    key = _key("GET", url, None)
    for d in _dirs():
        p = d / f"{key}.json"
        if p.exists():
            return _load(p)
    return None


def _candidates(props: dict) -> list[tuple[str, str]]:
    """(api_url, label) pairs to try first, derived from the artifact's page URL."""
    url = props.get("url") or ""
    out: list[tuple[str, str]] = []
    if m := re.search(r"usaspending\.gov/award/([^/?#]+)", url):
        out.append((f"{USA}/awards/{m.group(1)}/", "USAspending award detail"))
    if m := re.search(r"usaspending\.gov/recipient/([^/?#]+)", url):
        out.append((f"{USA}/recipient/{m.group(1)}/", "USAspending recipient"))
    if m := re.search(r"gleif\.org/#/record/([A-Z0-9]{20})", url):
        lei = m.group(1)
        out.append((f"https://api.gleif.org/api/v1/lei-records/{lei}", "GLEIF LEI record"))
    if m := re.search(r"littlesis\.org/org/(\d+)", url):
        out.append((f"https://littlesis.org/api/entities/{m.group(1)}", "LittleSis entity"))
    if m := re.search(r"littlesis\.org/relationships/(\d+)", url):
        out.append((f"https://littlesis.org/api/relationships/{m.group(1)}", "LittleSis relationship"))
    if m := re.search(r"browse-edgar\?action=getcompany&CIK=(\d+)", url):
        out.append((f"https://data.sec.gov/submissions/CIK{int(m.group(1)):010d}.json", "EDGAR submissions"))
    if m := re.search(r"Archives/edgar/data/(\d+)/(\d+)/", url):
        out.append((f"https://data.sec.gov/submissions/CIK{int(m.group(1)):010d}.json", "EDGAR submissions"))
    return out


def _tokens(props: dict) -> list[str]:
    """Distinctive identifiers for the fallback scan, most specific first."""
    url = props.get("url") or ""
    toks: list[str] = []
    for pat in (r"usaspending\.gov/award/([^/?#]+)", r"gleif\.org/#/record/([A-Z0-9]{20})", r"Archives/edgar/data/\d+/(\d+)/",
                r"littlesis\.org/(?:org|relationships)/(\d+)", r"sam\.gov/entity/([A-Z0-9]{12})"):
        if m := re.search(pat, url):
            toks.append(m.group(1))
    for k in ("award_id", "lei", "uei", "cik", "accession"):
        v = props.get(k)
        if v and len(str(v)) >= 4:
            toks.append(str(v))
    seen: set[str] = set()
    return [t for t in toks if not (t in seen or seen.add(t))]


def _narrow(body, tok: str):
    """Return the element of a list-shaped response that mentions the token, else None."""
    if isinstance(body, dict):
        # EDGAR submissions: parallel arrays under filings.recent — rebuild the one filing row.
        recent = (body.get("filings") or {}).get("recent") if isinstance(body.get("filings"), dict) else None
        if isinstance(recent, dict) and isinstance(recent.get("accessionNumber"), list):
            for i, accn in enumerate(recent["accessionNumber"]):
                if accn.replace("-", "") == tok.replace("-", ""):
                    return {k: v[i] for k, v in recent.items() if isinstance(v, list) and i < len(v)}
        for key in ("results", "data"):
            items = body.get(key)
            if isinstance(items, list):
                for it in items:
                    if tok in json.dumps(it, default=str):
                        return it
    return None


@functools.lru_cache(maxsize=256)
def _find_raw_cached(artifact_id: str, props_json: str, stamp: int) -> list[dict]:
    props = json.loads(props_json)
    hits: list[dict] = []
    files_seen: set[str] = set()
    for api_url, label in _candidates(props):
        doc = _by_url(api_url)
        if doc and doc["file"] not in files_seen:
            files_seen.add(doc["file"])
            body = doc["body"]
            for tok in _tokens(props):
                sub = _narrow(body, tok)
                if sub is not None:
                    body = sub
                    label += f" · row matching {tok}"
                    break
            hits.append({"url": doc["url"], "retrieved_at": doc["retrieved_at"], "match": label, "body": body})
    if hits:
        return hits
    toks = _tokens(props)
    if not toks:
        return hits
    # Full scan (a few MB, ~10 ms), then rank: responses from the artifact's own source first,
    # then ones where the token pinpointed a single row, so a SAM registration shows the SAM
    # response before a USAspending recipient record that merely mentions the same UEI.
    host = SOURCE_HOST.get(props.get("source") or "", "")
    found: list[tuple[int, int, dict]] = []
    for d in _dirs():
        for p in sorted(d.glob("*.json")):
            if p.name in files_seen:
                continue
            try:
                text = p.read_text()
            except Exception:
                continue
            tok = next((t for t in toks if t in text), None)
            if not tok:
                continue
            doc = _load(p)
            if not doc:
                continue
            files_seen.add(p.name)
            sub = _narrow(doc["body"], tok)
            same_source = 1 if host and host in (doc["url"] or "") else 0
            found.append((same_source, 1 if sub is not None else 0,
                          {"url": doc["url"], "retrieved_at": doc["retrieved_at"], "match": f"cached response containing {tok}" + (" · matching row" if sub is not None else ""),
                           "body": sub if sub is not None else doc["body"]}))
    found.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return hits + [f[2] for f in found[:MAX_HITS]]


def find_raw(artifact_id: str, props: dict) -> list[dict]:
    # stamp: the caches change when a seed or enrichment runs; bucket by the newest mtime so the memo stays fresh.
    stamp = 0
    for d in _dirs():
        try:
            stamp = max(stamp, int(d.stat().st_mtime))
        except OSError:
            pass
    clean = {k: v for k, v in props.items() if isinstance(v, (str, int, float, bool)) or v is None}
    return _find_raw_cached(artifact_id, json.dumps(clean, sort_keys=True, default=str), stamp)
