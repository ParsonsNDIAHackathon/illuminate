"""The capability contract — defined once, published to the in-app chat as tool
definitions and to outside agents over MCP (D1)."""
from __future__ import annotations

from ..cypher.templates import TEMPLATES
from ..styles import SWATCHES

TOOLS: list[dict] = [
    {
        "name": "search_entities",
        "description": "Find entities or people by name, alias, UEI, CAGE or LEI. Returns ids to use in other tools. Always search before proposing a new entity.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "kind": {"type": "string", "enum": ["entity", "person", "any"], "default": "any"},
                "limit": {"type": "integer", "default": 10, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": "expand_subgraph",
        "description": "Fetch the subgraph around an entity to a depth, honouring the workspace layer toggles. The result is drawn on the canvas.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "depth": {"type": "integer", "default": 2, "minimum": 1, "maximum": 6},
                "layers": {"type": "object", "description": "override toggles: {people, countries, artifacts, categories}"},
            },
            "required": ["entity_id"],
        },
    },
    {
        "name": "run_template",
        "description": "Run a saved, parameterised query template. Prefer this over run_cypher for the named intents. Templates: "
        + "; ".join(f"{t.name} — {t.description}" for t in TEMPLATES.values()),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "enum": list(TEMPLATES)},
                "params": {"type": "object", "description": "template parameters (entity_id/root_id/country/depth/…)"},
                "apply_styles": {"type": "boolean", "default": True, "description": "apply the template's default style_ops"},
            },
            "required": ["name", "params"],
        },
    },
    {
        "name": "run_cypher",
        "description": "Run a Cypher statement against the graph. Reads execute immediately (read-only, timeout, mandatory LIMIT). Anything that creates, modifies or deletes is previewed in a rolled-back transaction and held for the user's approval; a refusal comes back as a result so you can propose something narrower. Only schema labels/relationships are allowed. Return element ids (n.id, r.id) so you can style them.",
        "parameters": {
            "type": "object",
            "properties": {
                "statement": {"type": "string"},
                "params": {"type": "object"},
                "rationale": {"type": "string", "description": "one sentence shown to the user with the statement"},
            },
            "required": ["statement"],
        },
    },
    {
        "name": "propose_entity",
        "description": "Add an entity to the graph (after search_entities found nothing). Resolves identifiers first; the write itself goes through the permission gate.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "kind": {"type": "string", "enum": ["organization", "program", "agency"], "default": "organization"},
                "uei": {"type": "string"}, "cage": {"type": "string"}, "lei": {"type": "string"},
                "aliases": {"type": "array", "items": {"type": "string"}},
                "incorporated_in": {"type": "string", "description": "ISO2 country or 'US-XX' state code"},
                "manufactures_in": {"type": "array", "items": {"type": "string"}},
                "operates_in": {"type": "array", "items": {"type": "string"}},
                "provides": {"type": "array", "items": {"type": "string"}, "description": "category ids from the taxonomy"},
                "supplies_to": {
                    "type": "object",
                    "properties": {"entity_id": {"type": "string"}, "tier": {"type": "integer"}, "sole_source": {"type": "boolean"}, "contract_ref": {"type": "string"}},
                },
                "owned_by": {"type": "object", "properties": {"entity_id": {"type": "string"}, "pct": {"type": "number"}, "ultimate": {"type": "boolean"}}},
                "source_url": {"type": "string"},
                "rationale": {"type": "string"},
            },
            "required": ["name"],
        },
    },
    {
        "name": "attach_evidence",
        "description": "Attach evidence to an assertion: creates a Claim (subject, predicate, object) and an Artifact pointing at it. Goes through the permission gate.",
        "parameters": {
            "type": "object",
            "properties": {
                "subject_id": {"type": "string"},
                "predicate": {"type": "string", "description": "e.g. SUPPLIES, OWNS, HELD_ROLE, MANUFACTURES_IN, sanctions_screen, note"},
                "object_id": {"type": "string", "description": "node id when the object is a node"},
                "object_value": {"type": "string", "description": "literal when the object is a value"},
                "source_url": {"type": "string"},
                "title": {"type": "string"},
                "source": {"type": "string", "default": "user"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.7},
                "note": {"type": "string"},
            },
            "required": ["subject_id", "predicate", "source_url"],
        },
    },
    {
        "name": "set_styles",
        "description": "Change how elements are drawn. Ordered ops; fill/stroke are palette names only (" + ", ".join(SWATCHES) + "). The legend is derived from the ops' labels.",
        "parameters": {
            "type": "object",
            "properties": {
                "ops": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["clear", "set", "dim", "highlight", "hide"]},
                            "ids": {"type": "array", "items": {"type": "string"}},
                            "scope": {"type": "string", "enum": ["all", "nodes", "edges"]},
                            "style": {
                                "type": "object",
                                "properties": {
                                    "fill": {"type": "string", "enum": SWATCHES},
                                    "stroke": {"type": "string", "enum": SWATCHES},
                                    "badge": {"type": "string"},
                                    "size": {"type": "string", "enum": ["sm", "md", "lg", "xl"]},
                                    "shape": {"type": "string", "enum": ["ellipse", "rectangle", "diamond", "hexagon", "triangle"]},
                                    "dashed": {"type": "boolean"},
                                },
                            },
                            "label": {"type": "string", "description": "legend label for this op"},
                        },
                        "required": ["op"],
                    },
                }
            },
            "required": ["ops"],
        },
    },
    {
        "name": "get_entity_report",
        "description": "Standardised profile of one entity: identity, supply position, geography, control, people, risk indicators with citations, artifacts. This is the UC-11 projection.",
        "parameters": {"type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"]},
    },
    {
        "name": "enrich_entity",
        "description": "Queue background enrichment of an entity from the configured connectors (registry, ownership, sanctions, people, news, web). Facts arrive as Claims; authoritative connectors auto-commit, open-web facts wait for review.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string"},
                "connectors": {"type": "array", "items": {"type": "string"}, "description": "subset of connector names; default all connected"},
            },
            "required": ["entity_id"],
        },
    },
]

TOOL_NAMES = [t["name"] for t in TOOLS]


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in TOOLS]
