"""Connector contract (D5). A connector fetches from one source and *proposes*
facts. It never writes to the graph: the claims module stages every fact and a
trust rule — a property of the connector, not the model — decides what commits."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Literal

Trust = Literal["authoritative", "open"]


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@dataclass
class NodeRef:
    label: str                      # Entity | Person | Location | Category
    id: str
    props: dict = field(default_factory=dict)


@dataclass
class ArtifactRef:
    url: str
    title: str
    kind: str = "record"            # award | registry | filing | news | web | document | record
    source: str = ""
    published_at: str | None = None
    props: dict = field(default_factory=dict)


@dataclass
class Fact:
    """One proposed assertion: (subject)-[predicate {props}]->(object) or subject.attr = value."""
    subject: NodeRef
    predicate: str                  # relationship type, 'attr:<name>', or '<family>_screen'
    object: NodeRef | None = None
    value: str | None = None
    props: dict = field(default_factory=dict)
    artifact: ArtifactRef | None = None
    method: str = "connector"       # connector | model_extraction | fuzzy_match | human
    confidence: float = 0.9
    detail: str | None = None
    merge_keys: list[str] = field(default_factory=list)   # relationship props that identify a distinct edge (e.g. HELD_ROLE tenure)


class Connector:
    name: str = "base"
    label: str = "Base"
    description: str = ""
    trust: Trust = "open"
    key_name: str | None = None         # vault credential name, None when no key is needed
    key_url: str | None = None          # where a user registers for one
    key_note: str | None = None
    # Entity kinds this source can say anything about. A registry, sanctions list or
    # officer database speaks about companies; screening a *program* name against the
    # SDN list only manufactures noise, so the default excludes them.
    kinds: tuple[str, ...] = ("organization",)

    def needs_key(self) -> bool:
        return self.key_name is not None

    def applies_to(self, entity: dict) -> bool:
        return (entity.get("kind") or "organization") in self.kinds

    async def status(self, user: str) -> dict:
        from ..vault import vault
        if self.key_name and not vault().get(user, self.key_name):
            return {"connected": False, "detail": "Key needed", "needs_key": True}
        return {"connected": True, "detail": "no key required" if not self.key_name else f"api key {vault().masked(user).get(self.key_name, '····')}", "needs_key": bool(self.key_name)}

    async def enrich(self, entity: dict, user: str) -> list[Fact]:
        raise NotImplementedError

    def to_dict(self) -> dict:
        return {"name": self.name, "label": self.label, "description": self.description, "trust": self.trust,
                "key_name": self.key_name, "key_url": self.key_url, "key_note": self.key_note}
