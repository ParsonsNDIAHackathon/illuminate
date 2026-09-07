"""Open-web enrichment via the model's web-search tool (uses the user's OpenAI
key — no extra credential). Every extracted fact is a staged Claim that needs a
human or a second independent source (D5)."""
from __future__ import annotations

from ..ids import entity_id, location_id, normalize_name, normalize_person, person_id
from ..llm.client import client_for, models
from ..llm.tasks import extract_facts
from .base import ArtifactRef, Connector, Fact, NodeRef


class WebSearchConnector(Connector):
    name = "websearch"
    label = "Web search"
    description = "Open-web enrichment — model-extracted, staged for review"
    trust = "open"
    key_name = "openai"
    key_url = "https://platform.openai.com/api-keys"
    key_note = "Uses your OpenAI key (Responses API web_search tool)."

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        c = client_for(user)
        if not c:
            return []
        strong, fast = models(user)
        name = entity.get("legal_name") or entity["name"]
        try:
            resp = await c.responses.create(
                model=strong,
                tools=[{"type": "web_search"}],
                input=f"Research the company '{name}'. Report: ultimate parent / owners (with percentages if stated), country of incorporation, "
                      f"manufacturing locations, key executives and board members with titles, and what it supplies. Cite sources for every fact.",
            )
        except Exception as e:
            raise RuntimeError(f"web search failed: {e}")
        text = getattr(resp, "output_text", "") or ""
        urls: list[str] = []
        for item in getattr(resp, "output", []) or []:
            for part in getattr(item, "content", []) or []:
                for ann in getattr(part, "annotations", []) or []:
                    u = getattr(ann, "url", None)
                    if u and u not in urls:
                        urls.append(u)
        if not text:
            return []
        primary = urls[0] if urls else "https://www.openai.com/"
        facts_raw = await extract_facts(user, name, text, primary)
        subj = NodeRef("Entity", entity["id"])
        out: list[Fact] = []
        for f in facts_raw[:25]:
            pred, obj = f["predicate"], str(f["object"]).strip()
            conf = min(0.75, float(f.get("confidence") or 0.6))
            art = ArtifactRef(url=primary, title=f"Web research: {name}", kind="web", source="web", props={"quote": (f.get("quote") or "")[:400], "all_urls": urls[:10]})
            props = {"_model": strong}
            if pred in ("OWNS", "ULTIMATE_PARENT_OF"):
                pref = NodeRef("Entity", entity_id(name=obj), {"name": obj, "name_norm": normalize_name(obj), "kind": "organization", "source": "web"})
                pr = dict(props)
                if pred == "OWNS" and f.get("detail") and "%" in str(f["detail"]):
                    try:
                        pr["pct"] = float(str(f["detail"]).split("%")[0].split()[-1])
                    except Exception:
                        pass
                out.append(Fact(pref, pred, object=subj, props=pr, artifact=art, method="model_extraction", confidence=conf, detail=f.get("detail")))
            elif pred in ("INCORPORATED_IN", "MANUFACTURES_IN", "OPERATES_IN") and 2 <= len(obj) <= 6:
                code = obj.upper()
                out.append(Fact(subj, pred, object=NodeRef("Location", location_id(code), {"code": code, "name": code, "kind": "country" if len(code) == 2 else "region"}),
                                props=props, artifact=art, method="model_extraction", confidence=conf, detail=f.get("detail")))
            elif pred == "HELD_ROLE":
                pref = NodeRef("Person", person_id(obj, "web"), {"name": obj, "name_norm": normalize_person(obj), "source": "web"})
                title = f.get("detail") or "Officer"
                out.append(Fact(pref, "HELD_ROLE", object=subj, props={**props, "title": title, "role_type": "board" if "director" in title.lower() or "chair" in title.lower() else "executive", "current": True},
                                artifact=art, method="model_extraction", confidence=conf, merge_keys=["title"]))
            elif pred == "PROVIDES":
                kind = "goods" if "good" in obj.lower() or "manufactur" in obj.lower() else "services"
                out.append(Fact(subj, "PROVIDES", object=NodeRef("Category", f"cat_other_{kind}"), props=props, artifact=art, method="model_extraction", confidence=conf, detail=obj))
        return out
