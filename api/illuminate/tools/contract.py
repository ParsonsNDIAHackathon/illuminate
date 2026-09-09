"""The capability contract — defined once, published to the in-app chat as tool
definitions and to outside agents over MCP (D1)."""
from __future__ import annotations

from ..cypher.templates import TEMPLATES
from ..reports import DEFAULT_KIND as DEFAULT_REPORT_KIND, kinds as report_kinds
from ..schemes import catalog as scheme_catalog
from ..styles import SWATCHES

# Preset encodings are declared once, in schemes.py, for the same reason report kinds are:
# a scheme the contract advertises and the module cannot draw is a tool call that always fails.
SCHEMES = scheme_catalog()
SCHEME_NAMES = [s["name"] for s in SCHEMES]

# Report kinds are declared once, in reports.py, and published from there: a kind the contract
# knows about and the module cannot build would be a tool call that always fails.
REPORT_KINDS = report_kinds()
REPORT_KIND_NAMES = [k["kind"] for k in REPORT_KINDS]

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
                "layers": {"type": "object", "description": "override toggles: {people, countries, categories, artifacts, sources, claims}"},
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
                "keywords": {"type": "array", "items": {"type": "string"},
                             "description": "kind='program' only: the designations its contracts carry, e.g. ['E-2D']. What discover_suppliers searches award text for."},
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
        "description": "Change how elements are drawn. Ordered ops; fill/stroke are palette names only ("
                       + ", ".join(SWATCHES)
                       + "). The legend is derived from the ops' labels. Styling accumulates across turns: send only what this "
                         "turn adds, never an earlier turn's ops, and only emit 'clear' when the user asks to reset.",
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
                            "scope": {"type": "string", "enum": ["all", "nodes", "edges"], "description": "for clear, and for dim/hide with no ids: the whole canvas, or all nodes/edges"},
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
        "name": "apply_color_scheme",
        "description": "Colour the canvas with a preset scheme. Use this whenever the user asks for a standard encoding "
                       "— 'colour by risk', 'show me the risk gradient' — instead of querying scores and working out a "
                       "mapping with set_styles: the buckets, the thresholds and the ramp are fixed server-side, so the "
                       "same question gets the same picture every time and the legend comes back written. Schemes: "
                       + "; ".join(f"{s['name']} — {s['description']}" for s in SCHEMES) + ". "
                       "Like every other encoding this adds to what is already on the canvas; it does not clear it.",
        "parameters": {
            "type": "object",
            "properties": {
                "scheme": {"type": "string", "enum": SCHEME_NAMES},
                "ids": {"type": "array", "items": {"type": "string"},
                        "description": "restrict to these node ids; omit to colour everything the scheme can grade"},
            },
            "required": ["scheme"],
        },
    },
    {
        "name": "generate_report",
        "description": "Write a report and store it in the graph as a Report node, with its HTML document, the time it was "
                       "generated and the findings it made. Use this whenever the user asks for a report, an assessment or a "
                       "write-up — it is what produces a deliverable, where get_entity_report only hands you facts to talk about. "
                       "Kinds: " + "; ".join(f"{k['kind']} — {k['description']}" for k in REPORT_KINDS) + ". "
                       "The default is risk_assessment on the program the canvas is focused on. Regenerating the same kind for the "
                       "same subject rewrites that one report with current data rather than making a second one, so say so rather "
                       "than warning about duplicates. Say what the report found and that it is now on the Reports tab and on the canvas.",
        "parameters": {
            "type": "object",
            "properties": {
                "subject_id": {"type": "string", "description": "entity id the report is about; defaults to the focused program"},
                "kind": {"type": "string", "enum": REPORT_KIND_NAMES, "default": DEFAULT_REPORT_KIND},
            },
            "required": [],
        },
    },
    {
        "name": "get_entity_report",
        "description": "Standardised profile of one entity: identity, supply position, geography, control, people, risk indicators with citations, artifacts. This is the UC-11 projection.",
        "parameters": {"type": "object", "properties": {"entity_id": {"type": "string"}}, "required": ["entity_id"]},
    },
    {
        "name": "discover_suppliers",
        "description": "Build a program's supplier network from federal award records: prime recipients become tier-1 SUPPLIES edges and their reported sub-awardees tier-2. Use this for an entity of kind 'program' — enrich_entity asks what a *recipient* has won, which a program never has, so it finds nothing. "
                       "Keywords are matched against award text, so pick the designation the contracts actually carry ('E-2D', 'V-22', 'AN/APY-9') rather than the program's full title: a broad word pulls in unrelated companies that merely share it. "
                       "The search parameters are saved on the program so the discovery can be repeated and audited. Suppliers arrive with their award records as evidence; run enrich_entity on the interesting ones afterwards for identity, ownership, geography and screens.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_id": {"type": "string", "description": "id of the program entity"},
                "keywords": {"type": "array", "items": {"type": "string"}, "minItems": 1, "description": "award-text keywords, e.g. ['E-2D']"},
                "agency": {"type": "string", "description": "awarding agency filter; defaults to 'Department of Defense'. Empty string searches every agency."},
                "since": {"type": "string", "description": "award period start, YYYY-MM-DD (default 2019-10-01)"},
                "until": {"type": "string", "description": "award period end, YYYY-MM-DD (default 2026-09-30)"},
                "max_primes": {"type": "integer", "minimum": 1, "maximum": 100, "description": "how many top prime recipients to keep (default 20)"},
                "max_subs": {"type": "integer", "minimum": 0, "maximum": 200, "description": "how many top sub-awardees to keep (default 40); 0 skips the tier-2 pass"},
                "rationale": {"type": "string", "description": "one sentence shown to the user with the write"},
            },
            "required": ["entity_id", "keywords"],
        },
    },
    {
        "name": "enrich_entity",
        "description": "Queue background enrichment of an entity from the configured connectors (registry, ownership, sanctions, people, news, web). Facts arrive as Claims; authoritative connectors auto-commit, open-web facts wait for review. For a program, use discover_suppliers instead: the company-shaped sources are skipped for programs because screening a program name only manufactures noise.",
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
