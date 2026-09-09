"""Where an answer can send you (D6, same spirit as the style contract).

A chat turn regularly produces something the user then has to go and find: a report it
just wrote, an entity it just resolved, a person it named. Telling them "it is on the
Reports tab" is a navigation instruction the user has to execute by hand.

So a turn carries *links* the same way it carries style_ops: structured data the API
returns, not markup the model authors. A link names a destination inside the app; the
frontend decides what a destination looks like — a button under the message, a route push,
a node opened on the canvas — and the server never emits HTML or a URL it made up.

Two doors into the same model:

* **Structured** — a handler attaches `links` to its ToolResult (generate_report always
  does), so the button appears whether or not the model thought to mention it.
* **Written** — the model may put an in-app path in ordinary markdown, `[title](/reports/rp_x)`,
  and the chat renders it as navigation rather than a dead external link. The paths it is
  allowed to write are the ones listed here, and they are checked on the way in.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

LinkKind = Literal["report", "entity", "person", "canvas", "external"]

#: In-app routes a link may point at, mirroring web/src/router.ts. A path outside this set
#: is not a link — it is a 404 waiting to happen — so it is dropped rather than rendered.
ROUTE_PATTERNS: dict[str, re.Pattern[str]] = {
    "report": re.compile(r"^/reports/[\w.:-]+$"),
    "entity": re.compile(r"^/entities/[\w.:-]+$"),
    "person": re.compile(r"^/people/[\w.:-]+$"),
    "tab": re.compile(r"^/(reports|entities|people|risk|artifacts|claims|connectors|settings)$"),
}

#: "Put this node on the canvas" is an action, not a route, and gets its own scheme so the
#: frontend can tell the two apart without parsing labels.
CANVAS_SCHEME = "canvas:"


class Link(BaseModel):
    kind: LinkKind
    label: str = Field(max_length=120)
    href: str = Field(max_length=500)
    id: str | None = None
    description: str | None = Field(default=None, max_length=200)


def is_app_path(href: str) -> bool:
    """True for an in-app route this app actually has."""
    return any(p.match(href or "") for p in ROUTE_PATTERNS.values())


def report(report_id: str, title: str, *, subject_name: str | None = None) -> Link:
    return Link(kind="report", label=title, href=f"/reports/{report_id}", id=report_id,
                description=f"Open the report{f' on {subject_name}' if subject_name else ''}")


def entity(entity_id: str, name: str) -> Link:
    return Link(kind="entity", label=name, href=f"/entities/{entity_id}", id=entity_id,
                description="Open this entity's page")


def person(person_id: str, name: str) -> Link:
    return Link(kind="person", label=name, href=f"/people/{person_id}", id=person_id,
                description="Open this person's page")


def canvas(node_id: str, name: str) -> Link:
    """Show a node in context instead of on its own page — the other door (see
    web/src/composables/openOnCanvas.ts)."""
    return Link(kind="canvas", label=name, href=f"{CANVAS_SCHEME}{node_id}", id=node_id,
                description="Show it on the canvas")


def dump(links: list[Link]) -> list[dict]:
    return [l.model_dump(exclude_none=True) for l in links]


def link_contract_prompt() -> str:
    return (
        "LINKS: when your answer names something the user can open in this app, write it as an "
        "ordinary markdown link to the in-app path — [Risk assessment: E-2D](/reports/rp_abc123), "
        "[Acme Precision](/entities/ent_x), [Jane Doe](/people/per_y) — and the chat turns it into "
        "navigation. Use canvas:<node id> instead of a path to put a node on the canvas rather than "
        "open its page: [show it on the canvas](canvas:ent_x). Only these paths exist: /reports/<id>, "
        "/entities/<id>, /people/<id>, and the bare tabs /reports, /entities, /people, /risk, "
        "/artifacts, /claims, /connectors, /settings. Never invent another path, and never write a "
        "link to an id a tool did not return. Tools that produce something openable (generate_report) "
        "already attach a button, so mention the report by name and do not repeat the link."
    )
