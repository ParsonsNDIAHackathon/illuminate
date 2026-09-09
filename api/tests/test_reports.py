"""Report assembly and rendering.

Everything here is pure: findings in, a document out. The queries that gather findings are
exercised against a graph in test_reports_live.py; what this file protects is the part that
would be wrong in a way nobody notices — an entity name that closes a tag, a summary that
calls unscreened suppliers safe, a recommendation attached to a dimension that did not fire.
"""
import json

from illuminate import reports


def _finding(**kw):
    base = {
        "id": "ent_acme", "name": "Acme Castings", "score": 81, "band": "severe", "confidence": 74,
        "top_factor": "Foreign ownership and operations", "dimensions_scored": 5, "dimensions_requested": 7,
        "flagged": False, "simulated": False, "uei": "ABC123", "cage": None, "tier": 2,
        "chain": [{"id": "ent_acme", "name": "Acme Castings", "kind": "organization"},
                  {"id": "ent_prime", "name": "Prime Aero", "kind": "organization"},
                  {"id": "ent_prog", "name": "V-22 Osprey", "kind": "program"}],
        "hops": [{"id": "rel_1", "tier": 2, "sole_source": True, "contract_ref": "N0001-23-C-0001", "psc": "1560",
                  "naics": "336412", "source": "USAspending", "source_url": "https://example.gov/a", "simulated": False},
                 {"id": "rel_2", "tier": 1, "sole_source": False, "contract_ref": None, "psc": None, "naics": None,
                  "source": "USAspending", "source_url": None, "simulated": False}],
        "categories": [{"id": "cat_castings", "name": "Investment castings", "kind": "goods"}],
        "incorporated": "US", "parent_seat": "CN", "manufactures": ["CN"],
        "drivers": [{"dimension": "foreign", "family": "foreign", "label": "Ultimate parent seated in CN",
                     "severity": "high", "detail": "Covered nation", "source": "GLEIF",
                     "source_url": "https://gleif.org/x", "element_ids": ["ent_parent", "rel_own"], "weight": 1.5}],
    }
    base.update(kw)
    base.setdefault("sole_source", any(h["sole_source"] for h in base["hops"]))
    base["mitigations"] = reports.mitigations_for(base)
    base["element_ids"] = reports.element_ids(base)
    return base


def _data(findings=None, **kw):
    findings = _finding() if findings is None else findings
    findings = findings if isinstance(findings, list) else [findings]
    data = {
        "kind": "risk_assessment", "title": "Supply-chain risk assessment — V-22 Osprey",
        "subject": {"id": "ent_prog", "name": "V-22 Osprey", "kind": "program", "score": 63, "band": "high",
                    "top_factor": "Dependence on risky suppliers", "uei": None, "cage": None, "simulated": False},
        "findings": findings,
        "coverage": {"suppliers": 40, "scored": 31, "unscored": 9, "thin": 4, "flagged": 1, "depth": 4},
        "gaps": [{"id": "ent_gap", "name": "Quiet Machining", "consumer": "Prime Aero",
                  "contract_ref": "N0001-22-C-9", "psc": "1680", "tier": 2}],
        "sources": ["USAspending", "GLEIF"], "cited_ids": ["ent_acme"], "element_ids": ["ent_acme", "rel_1"],
        "simulated": False, "weights": {"designation": 3.0, "foreign": 1.5}, "reference": "Reference tables as of 2026-01",
        "depth": 4,
    }
    data.update(kw)
    return data


def test_element_ids_carry_the_route_and_the_evidence():
    """A finding the canvas cannot light up is an assertion. The supplier, every node and edge
    on its path, and whatever each dimension was computed from all have to come along."""
    ids = _finding()["element_ids"]
    assert ids[0] == "ent_acme"
    for expected in ("ent_prime", "ent_prog", "rel_1", "rel_2", "ent_parent", "rel_own"):
        assert expected in ids
    assert len(ids) == len(set(ids))


def test_mitigations_follow_the_dimensions_that_actually_fired():
    f = _finding()
    text = " ".join(f["mitigations"])
    assert f["mitigations"][0] == reports.VERIFY_FIRST
    assert "10 U.S.C." in text                      # the foreign dimension fired
    assert "insolvency" not in text                 # the financial one did not
    assert "sole-source" in text                    # and the path carries one

    clean = _finding(drivers=[], flagged=False, hops=[{"id": "rel_1", "tier": 1, "sole_source": False,
                                                       "contract_ref": None, "psc": None, "naics": None,
                                                       "source": None, "source_url": None, "simulated": False}])
    assert clean["mitigations"] == [reports.VERIFY_FIRST]


def test_a_flagged_supplier_gets_the_designation_steps_even_unscored():
    f = _finding(score=None, band=None, drivers=[], flagged=True)
    text = " ".join(f["mitigations"])
    assert "Confirm the match against the issuing list" in text
    assert "Enrich this supplier" in text


def test_the_summary_never_calls_unexamined_suppliers_safe():
    """The one sentence most likely to be read on its own. With nothing found it has to say
    what was looked at, because "no findings" over a third of the base unscreened is not a
    clean bill of health."""
    empty = reports._deterministic_summary(_data(findings=[]))
    assert "9 have never been scored" in empty
    assert "unexamined" in empty

    full = reports._deterministic_summary(_data())
    assert "Acme Castings" in full
    assert "sole-source" in full


def test_the_document_is_standalone_and_inert():
    doc = reports.render_risk_assessment(_data(), None, "2026-09-08T12:00:00Z")
    assert doc.startswith("<!doctype html>")
    assert "<style>" in doc and "<script" not in doc.lower()
    assert "V-22 Osprey" in doc
    assert "2026-09-08T12:00:00Z" in doc
    # Every section the assessment promises to answer.
    for heading in ("Summary", "Findings", "Irreplaceable and unexamined", "Method and limits", "Sources"):
        assert f">{heading}</h2>" in doc
    assert "Investment castings" in doc          # what is affected
    assert "Ultimate parent seated in CN" in doc  # where it comes from
    assert "10 U.S.C." in doc                     # what to do about it
    assert "N0001-23-C-0001" in doc               # the contract on the path
    assert "does not accuse" in doc


def test_a_hostile_name_cannot_close_a_tag():
    """Entity names come from registries, award text and the open web. The document is HTML
    the app hands to a browser, so every one of them is escaped, in the table and in the path."""
    nasty = '<img src=x onerror="alert(1)">Acme & Co "quoted"'
    doc = reports.render_risk_assessment(_data(findings=[_finding(name=nasty)]), None)
    assert "<img src=x" not in doc          # no tag survives
    assert 'onerror="' not in doc           # nor an attribute, quotes escaped too
    assert "&lt;img src=x" in doc           # it is shown, as text
    assert "Acme &amp; Co" in doc
    assert "&quot;quoted&quot;" in doc


def test_a_model_narrative_replaces_the_computed_one_and_is_attributed():
    doc = reports.render_risk_assessment(_data(), {"summary": "Three paths carry risk.",
                                                   "analyst_note": "Start with the castings house.",
                                                   "model": "gpt-5"}, None)
    assert "Three paths carry risk." in doc
    assert "Written by gpt-5" in doc
    assert "Analyst note" in doc
    assert "Start with the castings house." in doc


def test_simulated_material_is_disclosed_on_the_document():
    doc = reports.render_risk_assessment(_data(simulated=True), None)
    assert "Contains simulated data" in doc
    plain = reports.render_risk_assessment(_data(), None)
    assert "Contains simulated data" not in plain


def test_findings_are_the_only_thing_a_threshold_can_hide():
    """A supplier below the floor is left out of the findings; a designated one never is.
    The constants are the band floor, not a taste."""
    assert reports.FINDING_FLOOR == 25
    doc = reports.render_risk_assessment(_data(findings=[]), None)
    assert "25/100" in doc
    assert "not a clean bill of health" in doc


def test_kinds_are_published_with_a_builder_behind_each():
    for k in reports.kinds():
        spec = reports.KINDS[k["kind"]]
        assert callable(spec["assemble"]) and callable(spec["render"])
        assert k["label"] and k["description"]
    assert reports.DEFAULT_KIND in reports.KINDS


def test_the_tool_contract_offers_exactly_the_kinds_that_exist():
    from illuminate.tools.contract import TOOLS

    tool = next(t for t in TOOLS if t["name"] == "generate_report")
    assert set(tool["parameters"]["properties"]["kind"]["enum"]) == set(reports.KINDS)
    assert tool["parameters"]["properties"]["kind"]["default"] == reports.DEFAULT_KIND


def test_a_report_id_is_stable_per_kind_and_subject():
    """Regenerating has to rewrite one node. A dated id would leave a workspace full of
    documents nobody can tell apart."""
    from illuminate.ids import report_id

    assert report_id("risk_assessment", "ent_a") == report_id("risk_assessment", "ent_a")
    assert report_id("risk_assessment", "ent_a") != report_id("entity_profile", "ent_a")
    assert report_id("risk_assessment", "ent_a") != report_id("risk_assessment", "ent_b")
    assert report_id("risk_assessment", "ent_a").startswith("rep_")


def test_report_nodes_announce_themselves_like_any_other_write():
    """The canvas draws a new report without a reload, which only works if the delta walker
    recognises a rep_ id as a node id."""
    from illuminate import events

    assert events.node_ids({"id": "rep_abc123def"}) == ["rep_abc123def"]


def test_the_document_is_stripped_from_canvas_payloads():
    from illuminate.graphio import HEAVY_PROPS, layer_of

    assert "html" in HEAVY_PROPS
    assert layer_of("Report", {}) == "reports"


def test_entity_profile_renders_from_the_projection_report():
    """The profile is the page the Report button used to open, kept as a document instead."""
    rep = {
        "identity": {"id": "ent_x", "name": "Prime Aero", "uei": "U1", "cage": None, "lei": None, "kind": "organization",
                     "public": True, "ticker": "PA", "registration_status": "Active", "simulated": False,
                     "revenue": 1200000, "aliases": [], "org_types": [], "blurb": None, "lda_registrant_id": None},
        "geography": {"incorporated": {"code": "US"}, "parent_seat": {"code": "US"}, "manufactures": [{"code": "US"}],
                      "operates": []},
        "control": {"direct_parents": [{"id": "ent_p", "name": "Holdings", "pct": 60}], "ultimate_parents": []},
        "categories": [{"id": "cat_x", "name": "Engines & propulsion", "kind": "goods"}],
        "supply": {"supplies": [{"id": "ent_prog", "name": "V-22 Osprey", "tier": 1, "psc": "1560",
                                 "sole_source": True, "amount": 5000000, "contract_ref": "N1", "source": "USAspending",
                                 "source_url": None}],
                   "suppliers_count": 3, "sole_source_edges": 1, "tier_from_root": 1,
                   "awards": {"count": 2, "total": 5000000}},
        "people": {"current": [{"person_id": "per_1", "name": "R. Doe", "title": "CEO", "current": True, "from": "2020",
                                "to": None, "elsewhere": [], "edge_id": "rel_r"}],
                   "former": [], "board_size": None, "resolved_current_count": 1},
        "screens": [], "artifacts": [{"id": "art_1", "kind": "award", "title": "Award N1", "url": "https://x/y",
                                      "source": "USAspending", "retrieved_at": "2026-01-02T00:00:00Z",
                                      "published_at": None}],
        "news": [],
        "risk": {"indicators": [{"family": "foreign", "label": "Domestic ultimate parent", "severity": "clear",
                                 "source": "GLEIF", "detail": None, "element_ids": [], "scored": True}],
                 "composite": 22, "band": "low", "confidence": 61, "top_factor": None, "note": "note", "reference": None},
        "summary": {"text": "A prime.", "generated_at": "2026-01-02", "model": "gpt-5-mini", "source_count": 1},
        "sources": ["USAspending"], "entity": {}, "affiliations": {"count": 0},
    }
    data = {"kind": "entity_profile", "title": "Vendor profile — Prime Aero",
            "subject": {"id": "ent_x", "name": "Prime Aero", "kind": "organization", "score": 22, "band": "low",
                        "simulated": False},
            "report": rep, "sources": ["USAspending"], "cited_ids": ["ent_x"], "element_ids": ["ent_x"],
            "simulated": False, "reference": None}
    doc = reports.render_entity_profile(data, None, "2026-09-08T12:00:00Z")
    assert doc.startswith("<!doctype html>")
    assert "Prime Aero" in doc and "A prime." in doc
    assert "Engines &amp; propulsion" in doc
    assert "R. Doe" in doc
    assert "Award N1" in doc
    assert "does not accuse" in doc


def test_stored_breakdowns_are_read_never_recomputed():
    """A report must agree with the canvas and the entity list, and must not quietly run a
    scoring pass per finding — so it reads the stored column, and a node with nothing stored
    (or something unreadable in it) comes back absent rather than freshly scored."""
    import asyncio

    seen: dict = {}

    async def fake_read(cypher, params=None, **kw):
        seen["cypher"] = cypher
        seen["params"] = params
        return [
            {"id": "ent_scored", "components": json.dumps([{"dimension": "foreign", "severity": "high"}])},
            {"id": "ent_never", "components": None},
            {"id": "ent_broken", "components": "{not json"},
        ]

    real = reports.db.read
    reports.db.read = fake_read
    try:
        out = asyncio.run(reports._breakdowns(["ent_scored", "ent_never", "ent_broken"]))
        assert asyncio.run(reports._breakdowns([])) == {}
    finally:
        reports.db.read = real

    assert "risk_components" in seen["cypher"]
    assert set(out) == {"ent_scored"}
    assert out["ent_scored"][0]["severity"] == "high"
