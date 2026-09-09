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


REPORT_SYSTEM = (
    "You are writing the opening of a supply-chain risk assessment for a defence program office, from a JSON "
    "summary of findings a graph produced. Use ONLY those findings. Do not add companies, countries, "
    "relationships or numbers that are not in them, and do not soften or sharpen a severity the data gives you. "
    "Reply JSON {\"summary\": str, \"analyst_note\": str}. `summary` is 3-5 sentences: how many paths carry "
    "significant risk, which is the most exposed and why, what is affected, and how much of the supply base "
    "could actually be assessed — a supplier nothing is known about is unexamined, never safe. `analyst_note` is "
    "1-3 sentences on what to do first and what would settle the open questions. Neutral, specific, no "
    "hedging filler. This tool flags conditions warranting review; it never accuses anyone of wrongdoing."
)


async def report_narrative(user: str, data: dict) -> dict | None:
    """The prose a generated report carries on top of its computed findings (reports.py).

    Returns None whenever there is no key, no answer, or nothing for a model to add — the
    document is built from the graph either way and simply loses two paragraphs.
    """
    kind = data.get("kind")
    if kind == "entity_profile":
        # The profile already has a summarizer, and it reads the same facts. Reuse it rather
        # than teaching a second prompt the same job.
        rep = data.get("report") or {}
        return await summarize_entity(user, rep) if rep and not (rep.get("summary") or {}).get("text") else None
    if kind != "risk_assessment":
        return None
    facts = {
        "subject": {k: data["subject"].get(k) for k in ("name", "kind", "score", "band", "top_factor")},
        "coverage": data.get("coverage"),
        "findings": [{
            "supplier": f["name"], "tier": f["tier"], "score": f.get("score"), "band": f.get("band"),
            "leading_factor": f.get("top_factor"), "sole_source": f.get("sole_source"), "flagged": f.get("flagged"),
            "path": [n.get("name") for n in f.get("chain") or []],
            "goods": [c.get("name") for c in f.get("categories") or []],
            "drivers": [{"label": d.get("label"), "severity": d.get("severity"), "detail": d.get("detail")}
                        for d in (f.get("drivers") or [])[:4]],
        } for f in (data.get("findings") or [])[:15]],
        "unscreened_sole_sources": [g.get("name") for g in (data.get("gaps") or [])[:10]],
    }
    out = await _json_call(user, REPORT_SYSTEM, json.dumps(facts, default=str)[:14000], strong=True)
    if not out or not out.get("summary"):
        return None
    strong, _fast = models(user)
    return {"summary": out["summary"], "analyst_note": out.get("analyst_note"), "model": strong}


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
