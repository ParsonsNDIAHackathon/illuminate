"""Report generation against a real graph.

test_reports.py holds the rendering to account; this holds the queries. Findings are
gathered by walking supply edges and reading stored scores, and the only way to know that
those statements say what they mean is to run them over a small graph built here: a
program, a prime, a sole-source subcontractor with a score, and one supplier nobody has
scored at all. Everything it writes carries a testreports id and is deleted afterwards.
"""
import pytest

from illuminate import db, events, reports

PROG = "ent_testreports_prog"
PRIME = "ent_testreports_prime"
SUB = "ent_testreports_sub"
UNSCORED = "ent_testreports_unscored"

COMPONENTS = (
    '[{"family": "foreign", "dimension": "foreign", "label": "Ultimate parent seated in CN", '
    '"severity": "high", "source": "GLEIF", "detail": "Covered nation", "source_url": null, '
    '"element_ids": ["ent_testreports_sub"], "no_data": false, "weight": 1.5}, '
    '{"family": "media", "dimension": "media", "label": "Adverse media", "severity": "clear", '
    '"source": "GDELT", "detail": null, "source_url": null, "element_ids": [], "no_data": false, "weight": 0.75}]'
)


async def _reachable():
    await db.close_driver()  # the driver is bound to the previous test's event loop
    try:
        await db.read("RETURN 1 AS x")
        return True
    except Exception:
        return False


@pytest.fixture
async def graph():
    if not await _reachable():
        pytest.skip("neo4j not reachable")
    await db.write(
        """
        MERGE (p:Entity {id:$prog}) SET p.name='Testreports Program', p.kind='program'
        MERGE (a:Entity {id:$prime}) SET a.name='Testreports Prime', a.kind='organization', a.risk_score=30,
          a.risk_band='elevated', a.risk_confidence=70, a.risk_top_factor='Dependence on risky suppliers',
          a.risk_dimensions_scored=4, a.risk_dimensions_requested=7
        MERGE (b:Entity {id:$sub}) SET b.name='Testreports Castings', b.kind='organization', b.risk_score=88,
          b.risk_band='severe', b.risk_confidence=64, b.risk_top_factor='Ultimate parent seated in CN',
          b.risk_dimensions_scored=5, b.risk_dimensions_requested=7, b.risk_components=$components
        MERGE (u:Entity {id:$unscored}) SET u.name='Testreports Quiet Machining', u.kind='organization'
        MERGE (c:Category {id:'cat_castings_testreports'}) SET c.name='Investment castings', c.kind='goods'
        MERGE (b)-[:PROVIDES]->(c)
        MERGE (a)-[r1:SUPPLIES]->(p) SET r1.id='rel_testreports1', r1.tier=1, r1.psc='1560'
        MERGE (b)-[r2:SUPPLIES]->(a) SET r2.id='rel_testreports2', r2.tier=2, r2.sole_source=true,
          r2.contract_ref='TR-0001', r2.psc='1615', r2.source='USAspending'
        MERGE (u)-[r3:SUPPLIES]->(a) SET r3.id='rel_testreports3', r3.tier=2, r3.sole_source=true,
          r3.contract_ref='TR-0002'
        """,
        {"prog": PROG, "prime": PRIME, "sub": SUB, "unscored": UNSCORED, "components": COMPONENTS},
    )
    yield
    await db.write("MATCH (r:Report) WHERE r.subject_id STARTS WITH 'ent_testreports' DETACH DELETE r")
    await db.write("MATCH (e:Entity) WHERE e.id STARTS WITH 'ent_testreports' DETACH DELETE e")
    await db.write("MATCH (c:Category {id:'cat_castings_testreports'}) DETACH DELETE c")
    await db.close_driver()


async def test_findings_come_back_on_the_path_they_reach_the_program_by(graph):
    data = await reports.assemble_risk_assessment(PROG)
    by_name = {f["name"]: f for f in data["findings"]}
    assert set(by_name) == {"Testreports Castings", "Testreports Prime"}, "the unscored supplier is not a finding"

    sub = by_name["Testreports Castings"]
    assert sub["tier"] == 2
    assert [n["name"] for n in sub["chain"]] == ["Testreports Castings", "Testreports Prime", "Testreports Program"]
    assert [h["id"] for h in sub["hops"]] == ["rel_testreports2", "rel_testreports1"]
    assert sub["sole_source"] is True
    assert [c["name"] for c in sub["categories"]] == ["Investment castings"]
    # the stored breakdown, worst first, with `clear` dropped
    assert [d["severity"] for d in sub["drivers"]] == ["high"]
    assert sub["drivers"][0]["label"] == "Ultimate parent seated in CN"
    # findings are ordered by score, so the severe subcontractor leads the prime
    assert data["findings"][0]["name"] == "Testreports Castings"


async def test_coverage_counts_what_was_never_scored(graph):
    cov = await reports.coverage(PROG)
    assert cov["suppliers"] == 3
    assert cov["scored"] == 2
    assert cov["unscored"] == 1
    doc = reports.render_risk_assessment(await reports.assemble_risk_assessment(PROG), None)
    assert "1 has never been scored" in doc
    assert "unscored is not clear, it is unexamined" in doc


async def test_an_unscored_sole_source_gets_its_own_section(graph):
    gaps = await reports.unscreened_sole_sources(PROG)
    assert [g["name"] for g in gaps] == ["Testreports Quiet Machining"]
    assert gaps[0]["contract_ref"] == "TR-0002"
    doc = reports.render_risk_assessment(await reports.assemble_risk_assessment(PROG), None)
    assert "Testreports Quiet Machining" in doc
    assert "Irreplaceable and unexamined" in doc


async def test_generating_writes_a_node_that_points_at_its_subject_and_its_evidence(graph):
    seen = []

    async def listener(ev, payload):
        seen.append((ev, payload))

    events.add_listener(listener)
    try:
        row = await reports.generate("risk_assessment", PROG)
    finally:
        events.remove_listener(listener)

    assert row["finding_count"] == 2
    stored = await reports.get_report(row["id"])
    assert stored["html"].startswith("<!doctype html>")
    assert "Testreports Castings" in stored["html"]
    cited = {c["id"] for c in stored["cites"]}
    assert {SUB, PRIME} <= cited
    assert PROG not in cited, "the subject is joined by REPORTS_ON, not cited as its own finding"
    # relationship ids ride in element_ids for the canvas trace; CITES cannot carry them
    assert "rel_testreports2" in stored["element_ids"]

    edges = await db.read(
        "MATCH (r:Report {id:$id})-[e]->(n) RETURN type(e) AS t, n.id AS id ORDER BY t, id", {"id": row["id"]})
    assert {e["t"] for e in edges} == {"REPORTS_ON", "CITES"}
    assert [e["id"] for e in edges if e["t"] == "REPORTS_ON"] == [PROG]

    deltas = [p for e, p in seen if e == "graph_delta"]
    assert deltas and row["id"] in [n["id"] for n in deltas[-1]["subgraph"]["nodes"]], \
        "a new report reaches an open canvas the way any other write does"


async def test_regenerating_rewrites_the_same_node_with_current_findings(graph):
    first = await reports.generate("risk_assessment", PROG)
    await db.write("MATCH (b:Entity {id:$id}) SET b.risk_score=10, b.risk_band='low', b.risk_components=null",
                   {"id": SUB})
    second = await reports.generate("risk_assessment", PROG)

    assert second["id"] == first["id"]
    assert second["generated_at"] >= first["generated_at"]
    assert second["finding_count"] == 1, "the subcontractor dropped below the floor"
    n = await db.read("MATCH (r:Report) WHERE r.subject_id = $id RETURN count(*) AS n", {"id": PROG})
    assert n[0]["n"] == 1, "regenerating rewrites, it does not accumulate"

    stored = await reports.get_report(second["id"])
    assert SUB not in {c["id"] for c in stored["cites"]}, \
        "citations follow the findings; yesterday's evidence is not left pointing out of the document"


async def test_a_profile_can_be_written_about_any_entity(graph):
    row = await reports.generate("entity_profile", PRIME)
    stored = await reports.get_report(row["id"])
    assert "Testreports Prime" in stored["html"]
    assert "Testreports Program" in stored["html"], "its supply relationships are in the document"
    assert row["subject_id"] == PRIME


async def test_an_unknown_subject_or_kind_is_refused_before_anything_is_written(graph):
    with pytest.raises(reports.ReportError):
        await reports.generate("risk_assessment", "ent_testreports_nosuch")
    with pytest.raises(reports.ReportError):
        await reports.generate("no_such_kind", PROG)
    n = await db.read("MATCH (r:Report) WHERE r.subject_id STARTS WITH 'ent_testreports' RETURN count(*) AS n")
    assert n[0]["n"] == 0
