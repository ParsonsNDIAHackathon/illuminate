"""GDELT DOC 2.0 — recent news about an entity. Open, no key, aggressively
rate-limited (one request every ~5s; 429 otherwise). Artifacts are attached as
news; the adverse-media screen is computed from tone/sentiment when available."""
from __future__ import annotations

from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import HttpError, fetch_json

DOC = "https://api.gdeltproject.org/api/v2/doc/doc"


def _iso(seendate: str | None) -> str | None:
    # 20240503T121500Z → 2024-05-03
    if not seendate or len(seendate) < 8:
        return None
    return f"{seendate[0:4]}-{seendate[4:6]}-{seendate[6:8]}"


class GDELTConnector(Connector):
    name = "gdelt"
    label = "GDELT"
    description = "Recent news, entity clusters, tone"
    trust = "open"

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        facts: list[Fact] = []
        subj = NodeRef("Entity", entity["id"])
        q = f'"{entity.get("legal_name") or entity["name"]}"'
        try:
            res = await fetch_json("GET", DOC, params={"query": q, "mode": "artlist", "format": "json", "maxrecords": 15, "timespan": "3months", "sort": "datedesc"}, ttl=6 * 3600, timeout=40)
        except HttpError as e:
            if e.status == 429:
                raise RuntimeError("GDELT rate limit (429) — retry in a few minutes")
            raise
        arts = res.get("articles") or []
        titles = [a.get("title", "") for a in arts]
        labels = None
        try:
            from ..llm.tasks import sentiment
            labels = await sentiment(user, titles) if titles else None
        except Exception:
            labels = None
        neg = 0
        for i, a in enumerate(arts):
            sent = labels[i] if labels else None
            neg += 1 if sent == "negative" else 0
            art = ArtifactRef(url=a["url"], title=a.get("title") or a["url"], kind="news", source="GDELT", published_at=_iso(a.get("seendate")),
                              props={"domain": a.get("domain"), "language": a.get("language"), "sourcecountry": a.get("sourcecountry"), "sentiment": sent})
            facts.append(Fact(subj, "mention", artifact=art, confidence=0.5, detail="news mention"))
        if arts:
            sev = "medium" if neg >= 3 else ("low" if neg >= 1 else "clear")
            detail = f"{len(arts)} recent articles" + (f", {neg} negative" if labels else " (sentiment not scored — no model key)")
            facts.append(Fact(subj, "adverse_media_screen", value=sev if labels else "clear", confidence=0.6 if labels else 0.4, detail=detail,
                              artifact=ArtifactRef(url=f"https://api.gdeltproject.org/api/v2/doc/doc?query={q}&mode=artlist", title="GDELT article list", kind="record", source="GDELT")))
        return facts
