"""Market data for listed entities (Finnhub free tier). Keyed off by default —
almost no entity in a defence sub-tier graph is listed."""
from __future__ import annotations

from ..vault import vault
from .base import ArtifactRef, Connector, Fact, NodeRef
from .http import HttpError, fetch_json


class MarketConnector(Connector):
    name = "market"
    label = "Market data"
    description = "Quotes for listed entities (delayed)"
    trust = "authoritative"
    key_name = "finnhub"
    key_url = "https://finnhub.io/register"
    key_note = "Free tier key. Only applies to entities (or parents) with a ticker."

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        key = vault().get(user, self.key_name)
        ticker = entity.get("ticker")
        if not key or not ticker:
            return []
        try:
            q = await fetch_json("GET", "https://finnhub.io/api/v1/quote", params={"symbol": ticker, "token": key}, ttl=900)
            prof = await fetch_json("GET", "https://finnhub.io/api/v1/stock/profile2", params={"symbol": ticker, "token": key}, ttl=86400)
        except HttpError as e:
            raise RuntimeError(f"Finnhub: {e}")
        subj = NodeRef("Entity", entity["id"])
        art = ArtifactRef(url=f"https://finnhub.io/quote/{ticker}", title=f"Quote {ticker}", kind="record", source="Finnhub")
        facts = []
        if q.get("c"):
            facts.append(Fact(subj, "attr:last_price", value=str(q["c"]), artifact=art, confidence=0.9))
        if prof.get("marketCapitalization"):
            facts.append(Fact(subj, "attr:market_cap", value=str(prof["marketCapitalization"]), artifact=art, confidence=0.9))
        return facts
