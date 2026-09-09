from __future__ import annotations

import hashlib
import re
import unicodedata
import uuid

_SUFFIXES = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|llc|l\.l\.c|plc|gmbh|ag|sa|s\.a|nv|bv|pty|llp|lp|holdings?|group|the)\b\.?",
    re.I,
)


def normalize_name(name: str) -> str:
    """Normalise an organisation name for matching: case, punctuation, legal suffixes."""
    s = (name or "").lower()
    s = s.replace("&", " and ")
    s = re.sub(r"[^\w\s]", " ", s)
    s = _SUFFIXES.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_person(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"\b(mr|mrs|ms|dr|sir|jr|sr|ii|iii|phd|mba|esq)\b\.?", " ", s)
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def fold_text(s: str) -> str:
    """Case-, accent- and punctuation-insensitive form: "Société L-3 Harris" -> "societe l 3 harris"."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]|_", " ", s)).strip()


def search_tokens(query: str) -> list[str]:
    return [t for t in fold_text(query).split(" ") if t]


def lucene_query(query: str) -> str:
    """Fulltext query for a typed search: every word must match, each as exact, prefix or (for
    longer words) one-edit fuzzy, so "pame" finds Pamela, "wickam" finds Wickham, and "pamela wickham"
    does not drag in every other person with an "a" in their name. Tokens are folded to word characters so no
    Lucene syntax escaping is needed."""
    parts = []
    for t in search_tokens(query):
        alts = [t, f"{t}*"]
        if len(t) >= 4:
            alts.append(f"{t}~1")
        parts.append("(" + " OR ".join(alts) + ")")
    return " AND ".join(parts)


def name_match_score(a: str, b: str) -> float:
    """Similarity of two organisation names on a 0-100 scale, resistant to the
    subset trap: token_set_ratio scores 'Bell Boeing Joint Project Office' vs
    'Boeing' at 100, which is a false merge. Sorted-token similarity is the base;
    the set score only counts when the names are of comparable length."""
    from rapidfuzz import fuzz

    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 100.0
    score = fuzz.token_sort_ratio(na, nb)
    shorter, longer = sorted((len(na), len(nb)))
    if longer and shorter / longer >= 0.6:
        score = max(score, fuzz.token_set_ratio(na, nb))
    return float(score)


def stable_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha1("|".join(p or "" for p in parts).encode()).hexdigest()[:12]
    return f"{prefix}_{h}"


def entity_id(uei: str | None = None, lei: str | None = None, cage: str | None = None, name: str | None = None) -> str:
    if uei:
        return stable_id("ent", "uei", uei.upper())
    if lei:
        return stable_id("ent", "lei", lei.upper())
    if cage:
        return stable_id("ent", "cage", cage.upper())
    return stable_id("ent", "name", normalize_name(name or ""))


def person_id(name: str, source_ref: str | None = None) -> str:
    return stable_id("per", normalize_person(name), source_ref or "")


def location_id(code: str) -> str:
    return "loc_" + code.upper().replace(" ", "_")


def artifact_id(url: str) -> str:
    return stable_id("art", url)


def claim_id() -> str:
    return "clm_" + uuid.uuid4().hex[:12]


def report_id(kind: str, subject_id: str) -> str:
    """Stable per (kind, subject): asking twice for the risk assessment of a program gives
    the same node, and regenerating rewrites it rather than littering the graph with a
    dated pile of near-identical documents. The generated_at property is what moves."""
    return stable_id("rep", kind, subject_id)


def edge_id() -> str:
    return "rel_" + uuid.uuid4().hex[:12]
