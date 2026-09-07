"""Fast-tier model tasks (D8): classification, extraction, summaries. All are
optional — every caller degrades to no-data when there is no key."""
from __future__ import annotations

import json

from ..schema import TAXONOMY
from .client import client_for, models


async def _json_call(user: str, system: str, user_msg: str, *, strong: bool = False) -> dict | None:
    c = client_for(user)
    if not c:
        return None
    s, f = models(user)
    try:
        resp = await c.chat.completions.create(
            model=s if strong else f,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}],
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return None


async def classify_category(user: str, name: str, naics: str | None, psc: str | None, description: str | None) -> str | None:
    """Map an award/vendor to a taxonomy id. Returns None when no key or unsure."""
    tax = "\n".join(f"{c['id']}: {c['name']} [{c['kind']}]" for c in TAXONOMY if c["parent"])
    out = await _json_call(
        user,
        "Classify a defence vendor's supply into exactly one taxonomy id. Reply JSON {\"category_id\": str, \"confidence\": 0-1}. Taxonomy:\n" + tax,
        json.dumps({"vendor": name, "naics": naics, "psc": psc, "description": description}),
    )
    if out and out.get("category_id") in {c["id"] for c in TAXONOMY} and float(out.get("confidence", 0)) >= 0.5:
        return out["category_id"]
    return None


async def summarize_entity(user: str, report: dict) -> dict | None:
    """Model-written summary, labelled as such, from the report's own facts only."""
    facts = {k: report.get(k) for k in ("identity", "geography", "control", "categories", "supply", "screens", "news")}
    facts["people"] = {"current": [p["name"] + " — " + (p.get("title") or "") for p in report["people"]["current"][:8]]}
    out = await _json_call(
        user,
        "Write a 3-4 sentence neutral profile of this organisation using ONLY the facts given. Mention supply role, ownership/parent and jurisdiction, "
        "notable awards, and screening results. If a fact is absent say nothing about it. Never speculate or accuse. Reply JSON {\"summary\": str}.",
        json.dumps(facts, default=str)[:12000],
    )
    if out and out.get("summary"):
        s, f = models(user)
        return {"summary": out["summary"], "model": f}
    return None


async def extract_facts(user: str, entity_name: str, text: str, url: str) -> list[dict]:
    """Extract candidate facts about an entity from a web page. Each fact becomes a
    staged Claim (D5) — never a direct write."""
    out = await _json_call(
        user,
        "Extract verifiable corporate facts about the named organisation from the text. Allowed predicates: OWNS (object: parent company name, pct), "
        "ULTIMATE_PARENT_OF (object: parent name), INCORPORATED_IN (object: ISO2 country), MANUFACTURES_IN (ISO2 country), OPERATES_IN (ISO2 country), "
        "HELD_ROLE (object: person name; title; role_type executive|board), PROVIDES (goods|services description). "
        "Reply JSON {\"facts\": [{\"predicate\", \"object\", \"detail\", \"quote\", \"confidence\"}]}. Only include facts explicitly supported by a quote from the text.",
        json.dumps({"organisation": entity_name, "url": url, "text": text[:15000]}),
    )
    facts = (out or {}).get("facts") or []
    return [f for f in facts if isinstance(f, dict) and f.get("predicate") and f.get("object")]


async def sentiment(user: str, titles: list[str]) -> list[str] | None:
    out = await _json_call(
        user,
        "For each headline give sentiment toward the named organisation: positive, neutral or negative. Reply JSON {\"labels\": [..]} in order.",
        json.dumps(titles[:30]),
    )
    labels = (out or {}).get("labels")
    return labels if isinstance(labels, list) and len(labels) == len(titles[:30]) else None
