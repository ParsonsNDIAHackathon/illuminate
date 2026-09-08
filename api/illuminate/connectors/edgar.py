"""SEC EDGAR — company tickers, submissions (10-K, proxies, Forms 3/4/5). Open;
SEC requires a descriptive User-Agent, which the shared client sends."""
from __future__ import annotations

from datetime import date

from rapidfuzz import fuzz

from ..ids import name_match_score, normalize_name
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import HttpError, fetch_json

TICKERS = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
INTERESTING = {"10-K", "10-Q", "8-K", "DEF 14A", "20-F", "40-F", "3", "4", "5", "SC 13D", "SC 13G",
               # Notifications of late filing. A company files one of these when it cannot
               # close its books on time, which is the earliest public sign of trouble that
               # does not require reading the financials.
               "NT 10-K", "NT 10-Q", "NT 20-F"}
NT_FORMS = {"NT 10-K", "NT 10-Q", "NT 20-F"}
ANNUAL_FORMS = {"10-K", "20-F", "40-F"}
# An annual report older than this from a company still on the tape is a reporting gap.
ANNUAL_STALE_DAYS = 550


async def match_ticker(name: str) -> dict | None:
    try:
        data = await fetch_json("GET", TICKERS, ttl=7 * 86400)
    except HttpError:
        return None
    norm = normalize_name(name)
    best, best_s = None, 0
    for row in data.values():
        s = name_match_score(name, row.get("title", ""))
        if s > best_s:
            best, best_s = row, s
    return {**best, "score": best_s} if best and best_s >= 93 else None


async def submissions(cik: int) -> dict | None:
    try:
        return await fetch_json("GET", SUBMISSIONS.format(cik=int(cik)), ttl=86400)
    except HttpError:
        return None


class EDGARConnector(Connector):
    name = "edgar"
    label = "SEC EDGAR"
    description = "Filings, proxies, Forms 3/4/5 for listed entities"
    trust = "authoritative"
    key_note = "No key; SEC requires a descriptive User-Agent header (sent automatically)."

    async def status(self, user: str) -> dict:
        return {"connected": True, "detail": "UA header only", "needs_key": False}

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        facts: list[Fact] = []
        subj = NodeRef("Entity", entity["id"])
        cik = entity.get("cik")
        conf = 1.0
        if not cik:
            hit = await match_ticker(entity.get("legal_name") or entity["name"])
            if not hit:
                return facts
            cik = hit["cik_str"]
            conf = 0.85
        sub = await submissions(int(cik))
        if not sub:
            return facts
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={int(cik):010d}"
        art = ArtifactRef(url=url, title=f"EDGAR filings — {sub.get('name')}", kind="filing", source="EDGAR")
        facts.append(Fact(subj, "attr:cik", value=str(int(cik)), artifact=art, confidence=conf, method="fuzzy_match" if conf < 1 else "connector"))
        facts.append(Fact(subj, "attr:public", value="true", artifact=art, confidence=conf))
        tickers = sub.get("tickers") or []
        if tickers:
            facts.append(Fact(subj, "attr:ticker", value=tickers[0], artifact=art, confidence=conf))
        state = sub.get("stateOfIncorporation")
        if state:
            from ..ids import location_id
            code = f"US-{state}" if len(state) == 2 and state.isalpha() and state.upper() not in ("X1",) else state
            facts.append(Fact(subj, "INCORPORATED_IN", object=NodeRef("Location", location_id(code), {"code": code, "name": code, "kind": "region"}), artifact=art, confidence=conf,
                              detail="EDGAR state of incorporation"))
        recent = sub.get("filings", {}).get("recent", {})
        forms, dates, accs, docs = recent.get("form", []), recent.get("filingDate", []), recent.get("accessionNumber", []), recent.get("primaryDocument", [])
        n = 0
        seen: list[tuple[str, str]] = []
        for form, fdate, acc, doc in zip(forms, dates, accs, docs):
            seen.append((form, fdate))
            if form not in INTERESTING:
                continue
            accn = acc.replace("-", "")
            furl = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn}/{doc}"
            fart = ArtifactRef(url=furl, title=f"{form} filed {fdate}", kind="filing", source="EDGAR", published_at=fdate, props={"form": form})
            facts.append(Fact(subj, "mention", artifact=fart, confidence=conf, detail=f"{form} filing"))
            n += 1
            if n >= 12:
                break
        result, detail = grade_filings(seen, n)
        facts.append(Fact(subj, "financial_screen", value=result, artifact=art, confidence=0.7, detail=detail))
        return facts


def grade_filings(seen: list[tuple[str, str]], attached: int) -> tuple[str, str]:
    """Grade filing behaviour, which is all EDGAR's index can tell us without reading a
    financial statement. Two signals: a notification of late filing, and an annual report
    that has stopped arriving. Neither is a solvency judgement and the detail says so."""
    late = sorted({form for form, _ in seen if form in NT_FORMS})
    annuals = sorted((d for form, d in seen if form in ANNUAL_FORMS), reverse=True)
    latest_annual = annuals[0] if annuals else None
    stale = False
    if latest_annual:
        try:
            stale = (date.today() - date.fromisoformat(latest_annual[:10])).days > ANNUAL_STALE_DAYS
        except ValueError:
            stale = False
    parts = [f"{attached} recent filings attached"]
    if late:
        parts.append("late-filing notification on record (" + ", ".join(late) + ")")
    if latest_annual:
        parts.append(f"most recent annual report {latest_annual}" + (" — overdue" if stale else ""))
    else:
        parts.append("no annual report in the recent index")
    parts.append("filing behaviour only; no financial-statement analysis")
    result = "medium" if late else ("low" if stale or not latest_annual else "clear")
    return result, "; ".join(parts)
