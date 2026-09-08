"""DoD Section 1260H list — "Chinese military companies" operating in the United States.

Section 1260H of the FY2021 NDAA obliges the Department of Defense to publish the
companies it identifies as Chinese military companies. It is not a sanctions list: being
named carries no OFAC blocking, and from June 2026 the statute bars DoD from contracting
with a listed firm or with anything that supplies one. For a supply-chain graph that makes
it the third screen a vendor has to answer alongside OFAC and the UN, and the one that
most often lands two or three hops up an ownership chain rather than on the vendor itself.

DoD publishes the list as a PDF annex to a press release, not as a feed. Parsing that PDF
at screen time would make every screen depend on a document layout nobody controls, so the
roster is committed here instead, the way the seed commits its fixtures. It is an
**excerpt**, not the list: `COMPLETE = False`, and every screen result — clear ones
included — says so, because a clear result against a partial roster is not a clearance.

Screening is name-only. Nothing in the list carries a UEI, CAGE or LEI, so a hit is a lead
for an analyst to confirm against the published annex, and its confidence says that.
"""
from __future__ import annotations

from ..ids import name_match_score
from .base import ArtifactRef, Connector, Fact, NodeRef

LIST_PAGE = "https://www.defense.gov/News/Releases/Release/Article/3627271/dod-releases-list-of-chinese-military-companies-in-accordance-with-section-1260h/"
AS_OF = "2025-01"
COMPLETE = False
MATCH = 90

# name, then the aliases and English trading names a graph is likely to hold instead.
ROSTER: list[dict] = [
    {"name": "Aviation Industry Corporation of China", "aliases": ["AVIC", "AVIC International Holding Corporation"]},
    {"name": "China Aerospace Science and Technology Corporation", "aliases": ["CASC"]},
    {"name": "China Aerospace Science and Industry Corporation", "aliases": ["CASIC"]},
    {"name": "China Electronics Technology Group Corporation", "aliases": ["CETC"]},
    {"name": "China Electronics Corporation", "aliases": ["CEC"]},
    {"name": "China North Industries Group Corporation", "aliases": ["NORINCO", "NORINCO Group"]},
    {"name": "China South Industries Group Corporation", "aliases": ["CSGC"]},
    {"name": "China State Shipbuilding Corporation", "aliases": ["CSSC"]},
    {"name": "China Shipbuilding Industry Corporation", "aliases": ["CSIC"]},
    {"name": "China National Nuclear Corporation", "aliases": ["CNNC"]},
    {"name": "China General Nuclear Power Corporation", "aliases": ["CGN"]},
    {"name": "China Nuclear Engineering and Construction Corporation", "aliases": []},
    {"name": "Commercial Aircraft Corporation of China", "aliases": ["COMAC"]},
    {"name": "Aero Engine Corporation of China", "aliases": ["AECC"]},
    {"name": "China Academy of Launch Vehicle Technology", "aliases": ["CALT"]},
    {"name": "China Communications Construction Company", "aliases": ["CCCC"]},
    {"name": "China Railway Construction Corporation", "aliases": ["CRCC"]},
    {"name": "CRRC Corporation", "aliases": ["CRRC", "China Railway Rolling Stock Corporation"]},
    {"name": "China Mobile Communications Group", "aliases": ["China Mobile"]},
    {"name": "China Telecommunications Corporation", "aliases": ["China Telecom"]},
    {"name": "China United Network Communications Group", "aliases": ["China Unicom"]},
    {"name": "Huawei Technologies", "aliases": ["Huawei", "Huawei Investment & Holding"]},
    {"name": "Hangzhou Hikvision Digital Technology", "aliases": ["Hikvision"]},
    {"name": "Zhejiang Dahua Technology", "aliases": ["Dahua Technology"]},
    {"name": "Semiconductor Manufacturing International Corporation", "aliases": ["SMIC"]},
    {"name": "Yangtze Memory Technologies", "aliases": ["YMTC"]},
    {"name": "ChangXin Memory Technologies", "aliases": ["CXMT"]},
    {"name": "Inspur Group", "aliases": ["Inspur"]},
    {"name": "Hesai Technology", "aliases": ["Hesai Group"]},
    {"name": "China Telecommunications Technology", "aliases": []},
    {"name": "China Unicom (Hong Kong)", "aliases": []},
    {"name": "China National Offshore Oil Corporation", "aliases": ["CNOOC"]},
    {"name": "China National Chemical Corporation", "aliases": ["ChemChina"]},
    {"name": "Sinochem Group", "aliases": ["Sinochem"]},
    {"name": "China Minmetals Corporation", "aliases": ["Minmetals"]},
    {"name": "China Three Gorges Corporation", "aliases": ["Three Gorges"]},
    {"name": "China Merchants Group", "aliases": []},
    {"name": "China Academy of Engineering Physics", "aliases": ["CAEP"]},
    {"name": "China Electronics Technology Avionics", "aliases": []},
    {"name": "Beijing Institute of Technology", "aliases": []},
    {"name": "Harbin Institute of Technology", "aliases": []},
    {"name": "Beihang University", "aliases": ["Beijing University of Aeronautics and Astronautics"]},
    {"name": "Northwestern Polytechnical University", "aliases": []},
    {"name": "China Electronics Import and Export Corporation", "aliases": []},
    {"name": "Shenzhen DJI Sciences and Technologies", "aliases": ["DJI", "Da Jiang Innovations", "SZ DJI Technology"]},
    {"name": "Zhejiang Huahai Pharmaceutical", "aliases": []},
    {"name": "China Manned Space Engineering Office", "aliases": []},
    {"name": "Chengdu Aircraft Industrial Group", "aliases": ["Chengdu Aircraft"]},
    {"name": "Shenyang Aircraft Corporation", "aliases": ["Shenyang Aircraft"]},
    {"name": "Xi'an Aircraft Industrial Corporation", "aliases": ["Xian Aircraft"]},
    {"name": "Harbin Aircraft Industry Group", "aliases": []},
    {"name": "China Academy of Space Technology", "aliases": ["CAST"]},
    {"name": "China Satellite Network Group", "aliases": []},
    {"name": "Beijing Yunze Technology", "aliases": []},
    {"name": "Quectel Wireless Solutions", "aliases": ["Quectel"]},
    {"name": "China Aviation Industry General Aircraft", "aliases": []},
    {"name": "China Coast Guard", "aliases": []},
    {"name": "China Ocean Shipping Company", "aliases": ["COSCO", "COSCO Shipping"]},
]

LIST_NOTE = (
    f"Committed excerpt of the DoD Section 1260H list ({AS_OF}), {len(ROSTER)} designations; "
    "not the full annex. A clear result rules out these names only."
)


def screen(name: str, aliases: list[str] | None = None) -> dict:
    """Match an organisation name against the roster. Name-only: the list carries no
    registry identifiers, so a hit is a lead to confirm, never a determination."""
    queries = [n for n in [name, *(aliases or [])] if n]
    hits: list[dict] = []
    for row in ROSTER:
        candidates = [row["name"], *row["aliases"]]
        best, matched = 0.0, ""
        for q in queries:
            for candidate in candidates:
                s = name_match_score(q, candidate)
                if s > best:
                    best, matched = s, candidate
        if best >= MATCH:
            hits.append({"name": row["name"], "matched_name": matched, "score": best})
    hits.sort(key=lambda h: h["score"], reverse=True)
    return {"result": "hit" if hits else "clear", "hits": hits[:10], "list_size": len(ROSTER),
            "as_of": AS_OF, "complete": COMPLETE}


def describe(res: dict) -> str:
    if res["hits"]:
        body = "; ".join(f"{h['name']} (matched '{h['matched_name']}' at {h['score']:.0f})" for h in res["hits"][:3])
        return f"{body} · {LIST_NOTE}"
    return f"no match against {res['list_size']} designations · {LIST_NOTE}"


class Section1260HConnector(Connector):
    name = "section_1260h"
    label = "DoD Section 1260H"
    description = "Chinese military companies named by DoD under §1260H — restricted-list screen"
    trust = "authoritative"
    key_note = "No key. The roster is a committed excerpt of the published annex; see the screen detail for its date."

    async def status(self, user: str) -> dict:
        return {"connected": True, "detail": f"committed roster {AS_OF} · {len(ROSTER)} designations (excerpt)", "needs_key": False}

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        res = screen(entity["name"], entity.get("aliases"))
        subj = NodeRef("Entity", entity["id"])
        art = ArtifactRef(url=LIST_PAGE, title=f"DoD Section 1260H list ({AS_OF})", kind="record", source="U.S. Department of Defense")
        # A name-only hit is strong enough to commit and act on, but not strong enough to
        # claim certainty; a clear result against an excerpt is weaker still.
        conf = 0.8 if res["result"] == "hit" else 0.6
        return [Fact(subj, "restricted_list_screen", value=res["result"], artifact=art, confidence=conf, detail=describe(res))]
