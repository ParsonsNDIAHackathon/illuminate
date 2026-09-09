"""Preset colour schemes.

The ramp is a pure function of rows, so most of this reaches no graph. What it is really
guarding is the same rule the score itself keeps (test_risk_scoring.py): a node nobody
could grade is not a low-risk node. On a red-to-green ramp that failure mode is worse than
usual — silence would be painted the reassuring colour — so several of these exist only to
keep unscored nodes off the green end.
"""
from __future__ import annotations

import pytest

from illuminate import db, schemes
from illuminate.styles import PALETTE, derive_legend, validate_ops
from illuminate.tools.contract import TOOLS


def rows(*specs: tuple[str, int | None, str | None]) -> list[dict]:
    return [{"id": i, "score": s, "band": b, "confidence": 80} for i, s, b in specs]


def by_id(ops: list[dict]) -> dict[str, dict]:
    """Which op each node ended up in — the only thing the canvas cares about."""
    return {i: o for o in ops for i in o["ids"]}


# --- the ramp ----------------------------------------------------------------------
def test_ramp_runs_red_to_green_across_the_bands():
    ops = schemes._risk_ops(rows(("a", 90, "severe"), ("b", 60, "high"), ("c", 30, "elevated"), ("d", 5, "low")))
    fills = {i: o["style"]["fill"] for i, o in by_id(ops).items()}
    assert fills == {"a": "red", "b": "orange", "c": "yellow", "d": "green"}


def test_bands_are_the_stored_thresholds_not_new_ones():
    from illuminate import risk
    assert [b for b, _, _ in schemes.RISK_RAMP] == [name for _, name in risk.BANDS]


def test_a_score_with_no_stored_band_is_graded_rather_than_dropped():
    ops = by_id(schemes._risk_ops(rows(("a", 80, None))))
    assert ops["a"]["style"]["fill"] == "red"


def test_one_op_per_band_not_one_per_node():
    ops = schemes._risk_ops(rows(("a", 90, "severe"), ("b", 80, "severe"), ("c", 5, "low")))
    assert len(ops) == 2
    assert sorted(ops[0]["ids"]) == ["a", "b"]


def test_empty_bands_produce_no_op():
    ops = schemes._risk_ops(rows(("a", 90, "severe")))
    assert [o["label"] for o in ops] == ["Severe (75+)"]


# --- unscored is not low -----------------------------------------------------------
def test_unscored_is_never_painted_a_ramp_colour():
    op = by_id(schemes._risk_ops(rows(("a", None, None))))["a"]
    assert "fill" not in op["style"]
    assert op["style"]["stroke"] == "neutral"
    assert op["style"]["dashed"] is True


def test_unscored_says_so_in_the_legend():
    ops = validate_ops(schemes._risk_ops(rows(("a", 90, "severe"), ("b", None, None))))
    labels = [l.label for l in derive_legend(ops)]
    assert "Unscored — nothing to grade" in labels


def test_unscored_is_counted_and_explained_in_the_note():
    note = schemes._risk_note(rows(("a", 90, "severe"), ("b", None, None), ("c", None, None)))
    assert "2 unscored" in note
    assert "not the same as low risk" in note


def test_a_band_the_ramp_does_not_know_is_treated_as_ungraded():
    """A hand-set risk_band ('critical', say) must not silently fall into a colour."""
    op = by_id(schemes._risk_ops([{"id": "a", "score": 90, "band": "critical", "confidence": 80}]))["a"]
    assert "fill" not in op["style"]


def test_thin_scores_are_reported_but_still_coloured():
    r = [{"id": "a", "score": 90, "band": "severe", "confidence": 20}]
    assert by_id(schemes._risk_ops(r))["a"]["style"]["fill"] == "red"
    assert "thin" in schemes._risk_note(r)


# --- the contract ------------------------------------------------------------------
def test_ops_pass_the_style_contract():
    ops = validate_ops(schemes._risk_ops(rows(("a", 90, "severe"), ("b", None, None))))
    for o in ops:
        assert o.op == "set" and o.label
        for swatch in (o.style.fill, o.style.stroke):
            assert swatch is None or swatch in PALETTE


def test_the_tool_advertises_exactly_the_schemes_that_exist():
    tool = next(t for t in TOOLS if t["name"] == "apply_color_scheme")
    assert tool["parameters"]["properties"]["scheme"]["enum"] == list(schemes.SCHEMES)


async def test_unknown_scheme_is_an_error_not_an_empty_canvas():
    with pytest.raises(schemes.UnknownScheme):
        await schemes.apply("chartreuse")


async def test_the_tool_colours_what_the_caller_has_on_screen(monkeypatch):
    """A legend that counts 350 low-risk nodes over a canvas showing thirty is a lie about
    what the user is looking at, so with no ids the scheme takes the canvas."""
    from illuminate.tools.handlers import ToolContext, apply_color_scheme

    seen = {}

    async def fake_apply(name, ids=None, limit=schemes.MAX_NODES):
        seen["ids"] = ids
        return {"scheme": name, "label": name, "style_ops": [], "legend": [], "node_count": 0, "note": ""}

    monkeypatch.setattr(schemes, "apply", fake_apply)
    await apply_color_scheme(ToolContext(source="chat", canvas_ids=["a", "b"]), "risk")
    assert seen["ids"] == ["a", "b"]
    # an agent with no canvas gets the whole graph
    await apply_color_scheme(ToolContext(source="mcp"), "risk")
    assert seen["ids"] is None


# --- against a graph ---------------------------------------------------------------
PROG = "ent_testschemes_prog"
HOT = "ent_testschemes_hot"
QUIET = "ent_testschemes_quiet"


async def _reachable() -> bool:
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
        MERGE (p:Entity {id:$prog}) SET p.name='Testschemes Program', p.kind='program'
        MERGE (h:Entity {id:$hot}) SET h.name='Testschemes Castings', h.kind='organization',
          h.risk_score=88, h.risk_band='severe', h.risk_confidence=64
        MERGE (q:Entity {id:$quiet}) SET q.name='Testschemes Quiet', q.kind='organization'
        MERGE (h)-[s:SUPPLIES {id:'rel_testschemes_1'}]->(p)
        RETURN 1 AS ok
        """,
        {"prog": PROG, "hot": HOT, "quiet": QUIET},
    )
    yield
    await db.write("MATCH (n) WHERE n.id STARTS WITH 'ent_testschemes' DETACH DELETE n")


async def test_apply_colours_the_ids_it_was_given(graph):
    out = await schemes.apply("risk", [PROG, HOT, QUIET])
    assert out["scheme"] == "risk"
    assert out["node_count"] == 3
    painted = by_id(out["style_ops"])
    assert painted[HOT]["style"]["fill"] == "red"
    # the program and the unscored supplier are outlined, not ranked
    assert "fill" not in painted[QUIET]["style"]
    assert {l["label"] for l in out["legend"]} == {"Severe (75+)", "Unscored — nothing to grade"}


async def test_apply_leaves_out_nodes_it_was_not_given(graph):
    out = await schemes.apply("risk", [HOT])
    assert list(by_id(out["style_ops"])) == [HOT]


async def test_an_empty_selection_colours_nothing_rather_than_everything(graph):
    """A canvas with nothing on it asks about no nodes — which is not the same question as
    asking about all of them."""
    out = await schemes.apply("risk", [])
    assert out["style_ops"] == [] and out["node_count"] == 0
