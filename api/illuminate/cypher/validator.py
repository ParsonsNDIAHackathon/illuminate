"""Static Cypher validator (D3).

Every statement — generated or hand-written — is classified before anything
executes: READ, WRITE, DESTRUCTIVE or SCHEMA. Reads execute immediately under a
read-only session, a timeout and a mandatory LIMIT. Everything else routes to the
permission gate. The validator also enforces an allowlist of labels, relationship
types and APOC procedures, caps variable-length hops, and rejects CALL db.* /
dbms.* and LOAD CSV outright.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ..config import settings
from ..schema import APOC_ALLOWLIST, APOC_WRITE_ALLOWLIST, LABELS, RELS

Classification = Literal["READ", "WRITE", "DESTRUCTIVE", "SCHEMA"]


class CypherRejected(Exception):
    def __init__(self, reason: str, statement: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.statement = statement


@dataclass
class Validated:
    original: str
    statement: str  # possibly rewritten (LIMIT appended / clamped)
    classification: Classification
    labels: set[str] = field(default_factory=set)
    rel_types: set[str] = field(default_factory=set)
    procedures: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    @property
    def is_read(self) -> bool:
        return self.classification == "READ"


# ---------------------------------------------------------------------------------
_STRING = re.compile(r"""("(?:\\.|[^"\\])*")|('(?:\\.|[^'\\])*')""", re.S)
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.S)


def strip_strings_and_comments(q: str) -> str:
    q = _BLOCK_COMMENT.sub(" ", q)
    q = _LINE_COMMENT.sub(" ", q)
    # keep quotes so token boundaries survive, blank the contents
    q = _STRING.sub(lambda m: '"' + " " * (len(m.group(0)) - 2) + '"', q)
    return q


_BLOCKED = [
    (re.compile(r"\bCALL\s+db\s*\.", re.I), "CALL db.* is not permitted"),
    (re.compile(r"\bCALL\s+dbms\s*\.", re.I), "CALL dbms.* is not permitted"),
    (re.compile(r"\bLOAD\s+CSV\b", re.I), "LOAD CSV is not permitted"),
    (re.compile(r"\bapoc\.(load|import|export|systemdb|trigger|custom|periodic|cypher\.run|cypher\.do|util\.sleep|log|config|monitor|schema|bolt|es|mongo|redis|couchbase|uuid\.setup|ttl|static|warmup)\b", re.I),
     "that APOC namespace is not permitted"),
    (re.compile(r"\bUSE\s+[A-Za-z_]", re.I), "USE <database> is not permitted"),
    (re.compile(r"\bIN\s+TRANSACTIONS\b", re.I), "CALL { } IN TRANSACTIONS is not permitted"),
    (re.compile(r"^\s*:", re.M), "shell commands are not permitted"),
    (re.compile(r"\b(SHOW|TERMINATE)\s+(USERS?|ROLES?|DATABASES?|TRANSACTIONS?|PRIVILEGES?|SERVERS?|ALIASES?)\b", re.I), "administration commands are not permitted"),
    (re.compile(r"\b(CREATE|DROP|ALTER|START|STOP)\s+(DATABASE|USER|ROLE|ALIAS|SERVER)\b", re.I), "administration commands are not permitted"),
    (re.compile(r"\b(GRANT|DENY|REVOKE)\b", re.I), "privilege commands are not permitted"),
]

_SCHEMA = re.compile(r"\b(CREATE|DROP)\s+(CONSTRAINT|INDEX|FULLTEXT|TEXT|POINT|RANGE|LOOKUP|VECTOR)\b", re.I)
_DESTRUCTIVE = re.compile(r"\b(DETACH\s+DELETE|DELETE|REMOVE)\b", re.I)
_WRITE = re.compile(r"\b(CREATE|MERGE|SET|FOREACH)\b", re.I)
_WRITE_APOC = re.compile(r"\bapoc\.(create|merge|refactor|nodes\.delete|atomic)\b", re.I)
_DESTRUCTIVE_APOC = re.compile(r"\bapoc\.(refactor|nodes\.delete|atomic\.remove)\b", re.I)

_LABEL = re.compile(r"(?<![\w$])(?:\(\s*[A-Za-z_][\w]*\s*)?:\s*`?([A-Za-z_][\w]*)`?")
_NODE_LABEL = re.compile(r"\(\s*(?:[A-Za-z_]\w*)?\s*((?::\s*`?[A-Za-z_]\w*`?\s*(?:[|&]\s*)?)+)")
_REL_TYPE = re.compile(r"\[\s*(?:[A-Za-z_]\w*)?\s*((?::\s*`?[A-Za-z_]\w*`?\s*(?:\|\s*:?\s*)?)+)")
_INLINE_LABEL = re.compile(r"\b[A-Za-z_]\w*\s*:\s*`?([A-Za-z_]\w*)`?(?!\s*[:\w])")  # n:Label in WHERE / WITH n:Label
_PROC = re.compile(r"\b(apoc(?:\.[A-Za-z_]\w*)+)\s*\(", re.I)
_VARLEN = re.compile(r"\*\s*(\d+)?\s*(?:\.\.\s*(\d+)?)?\s*(?=[\]\s{])")
_LIMIT = re.compile(r"\bLIMIT\s+(\d+|\$\w+)\s*;?\s*$", re.I)
_LIMIT_ANY = re.compile(r"\bLIMIT\s+(\d+)", re.I)
_TERMINAL_RETURN = re.compile(r"\bRETURN\b", re.I)

_ALLOWED_LABELS = set(LABELS)
_ALLOWED_RELS = set(RELS)


def _names_from_group(group: str) -> list[str]:
    return [n for n in re.findall(r"`?([A-Za-z_]\w*)`?", group)]


def extract_labels_and_rels(clean: str) -> tuple[set[str], set[str]]:
    labels: set[str] = set()
    rels: set[str] = set()
    for m in _NODE_LABEL.finditer(clean):
        labels.update(_names_from_group(m.group(1)))
    for m in _REL_TYPE.finditer(clean):
        rels.update(_names_from_group(m.group(1)))
    # `WHERE n:Entity` / `WITH n:Entity AS x` forms
    for m in re.finditer(r"\b([A-Za-z_]\w*)\s*:\s*`?([A-Za-z_]\w*)`?", clean):
        var, lab = m.group(1), m.group(2)
        # Skip map-literal keys ({tier: 3}) — they are preceded by '{' or ','
        start = m.start()
        prev = clean[:start].rstrip()[-1:] if clean[:start].rstrip() else ""
        # '[r:TYPE' and '(n:Label' were handled by the pattern regexes above.
        if prev in "{,[(|":
            continue
        if lab in _ALLOWED_RELS:
            continue
        if var.lower() in ("http", "https", "bolt"):
            continue
        labels.add(lab)
    return labels, rels


def classify(clean: str) -> Classification:
    if _SCHEMA.search(clean):
        return "SCHEMA"
    if _DESTRUCTIVE.search(clean) or _DESTRUCTIVE_APOC.search(clean):
        return "DESTRUCTIVE"
    if _WRITE.search(clean) or _WRITE_APOC.search(clean):
        return "WRITE"
    return "READ"


def validate(statement: str, *, params: dict | None = None) -> Validated:
    if not statement or not statement.strip():
        raise CypherRejected("empty statement")
    stripped = statement.strip().rstrip(";").strip()
    if ";" in strip_strings_and_comments(stripped):
        raise CypherRejected("multiple statements are not permitted", statement)
    clean = strip_strings_and_comments(stripped)

    for rx, reason in _BLOCKED:
        if rx.search(clean):
            raise CypherRejected(reason, statement)

    labels, rels = extract_labels_and_rels(clean)
    bad_labels = {l for l in labels if l not in _ALLOWED_LABELS}
    bad_rels = {r for r in rels if r not in _ALLOWED_RELS}
    if bad_labels:
        raise CypherRejected(f"label(s) not in schema: {', '.join(sorted(bad_labels))}", statement)
    if bad_rels:
        raise CypherRejected(f"relationship type(s) not in schema: {', '.join(sorted(bad_rels))}", statement)

    procs = {m.group(1).lower() for m in _PROC.finditer(clean)}
    for p in procs:
        ok = any(p.startswith(a.lower()) for a in APOC_ALLOWLIST + APOC_WRITE_ALLOWLIST)
        if not ok:
            raise CypherRejected(f"procedure not allowlisted: {p}", statement)

    for m in _VARLEN.finditer(clean):
        lo, hi = m.group(1), m.group(2)
        upper = hi or (lo if (lo and ".." not in m.group(0)) else None)
        if upper is None:
            raise CypherRejected(f"unbounded variable-length pattern; cap hops at {settings.cypher_max_hops}", statement)
        if int(upper) > settings.cypher_max_hops:
            raise CypherRejected(f"variable-length pattern exceeds {settings.cypher_max_hops} hops", statement)

    cls = classify(clean)
    notes: list[str] = []
    out = stripped
    if cls == "READ":
        out, note = enforce_limit(stripped, clean, params or {})
        if note:
            notes.append(note)
    return Validated(original=statement, statement=out, classification=cls, labels=labels, rel_types=rels, procedures=procs, notes=notes)


def enforce_limit(stmt: str, clean: str, params: dict) -> tuple[str, str | None]:
    """Reads carry a mandatory LIMIT. Missing → append default; too large → clamp."""
    m = _LIMIT.search(clean)
    if m:
        tok = m.group(1)
        if tok.startswith("$"):
            v = params.get(tok[1:])
            if isinstance(v, int) and v > settings.cypher_max_limit:
                params[tok[1:]] = settings.cypher_max_limit
                return stmt, f"LIMIT parameter clamped to {settings.cypher_max_limit}"
            return stmt, None
        n = int(tok)
        if n > settings.cypher_max_limit:
            new = re.sub(r"\bLIMIT\s+\d+\s*$", f"LIMIT {settings.cypher_max_limit}", stmt, flags=re.I)
            return new, f"LIMIT clamped to {settings.cypher_max_limit}"
        return stmt, None
    if _TERMINAL_RETURN.search(clean):
        return f"{stmt}\nLIMIT {settings.cypher_default_limit}", f"LIMIT {settings.cypher_default_limit} appended"
    return stmt, None


def is_pure_create(clean_statement: str) -> bool:
    """Heuristic for the 'auto-approve creates' mode: CREATE/MERGE with SET only
    inside ON CREATE, no DELETE/REMOVE."""
    clean = strip_strings_and_comments(clean_statement)
    if _DESTRUCTIVE.search(clean):
        return False
    # Any SET not preceded by ON CREATE is a modify.
    for m in re.finditer(r"\bSET\b", clean, re.I):
        before = clean[: m.start()].rstrip()
        if not re.search(r"\bON\s+CREATE\s*$", before, re.I):
            return False
    return bool(_WRITE.search(clean))
