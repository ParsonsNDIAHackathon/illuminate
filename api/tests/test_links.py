"""Where an answer can send you.

A link is only useful if the route exists, so the thing worth testing is that every link
the server can build lands on a path web/src/router.ts actually serves, and that anything
else is refused rather than rendered as a dead button.
"""
from __future__ import annotations

import re
from pathlib import Path

from illuminate import links


def test_every_builder_produces_a_route_the_app_has():
    for link in (links.report("rp_1", "Risk assessment"), links.entity("ent_1", "Acme"), links.person("per_1", "Jane Doe")):
        assert links.is_app_path(link.href), link.href


def test_canvas_links_are_an_action_not_a_route():
    link = links.canvas("ent_1", "Acme")
    assert link.href == "canvas:ent_1"
    assert not links.is_app_path(link.href)


def test_invented_paths_are_not_app_paths():
    for href in ("/report/rp_1", "/entities", "/entities/ent_1/edit", "https://example.com/reports/rp_1", "", "//evil.example.com"):
        assert not links.ROUTE_PATTERNS["report"].match(href)
    assert not links.is_app_path("/dashboard")
    assert links.is_app_path("/entities")   # a bare tab is a real route


def test_report_link_names_its_subject():
    link = links.report("rp_1", "Risk assessment: E-2D", subject_name="E-2D")
    assert link.kind == "report" and link.id == "rp_1"
    assert "E-2D" in (link.description or "")


def test_dump_drops_empty_fields():
    assert links.dump([links.entity("ent_1", "Acme")]) == [
        {"kind": "entity", "label": "Acme", "href": "/entities/ent_1", "id": "ent_1", "description": "Open this entity's page"}
    ]


async def test_writing_a_report_hands_back_the_door_to_it(monkeypatch):
    """The point of the whole feature: a report the chat just wrote is one click away, and
    it is the handler that guarantees it rather than the model remembering to say so."""
    from illuminate import events, reports
    from illuminate.tools.handlers import ToolContext, generate_report

    async def fake_generate(kind, subject_id, *, user="local"):
        return {"id": "rp_risk_ent_1", "kind": kind, "title": "Risk assessment: E-2D",
                "subject_id": subject_id, "subject_name": "E-2D", "finding_count": 4}

    monkeypatch.setattr(reports, "generate", fake_generate)
    monkeypatch.setattr(events, "delta_for", lambda ids: _empty())

    r = await generate_report(ToolContext(source="chat"), subject_id="ent_1")
    assert r.ok
    assert r.links == [{"kind": "report", "label": "Risk assessment: E-2D", "href": "/reports/rp_risk_ent_1",
                        "id": "rp_risk_ent_1", "description": "Open the report on E-2D"}]


async def _empty():
    return {"nodes": [], "edges": []}


def test_route_patterns_match_the_frontend_router():
    """The paths this module will emit have to be paths the router declares. Both lists are
    short and both are hand-maintained, so this is the thing that catches the drift."""
    router = (Path(__file__).resolve().parents[2] / "web" / "src" / "router.ts").read_text()
    declared = set(re.findall(r"path:\s*'([^']+)'", router))
    for path in ("/reports/:id", "/entities/:id", "/people/:id", "/risk", "/artifacts", "/claims", "/connectors", "/settings"):
        assert path in declared, path
