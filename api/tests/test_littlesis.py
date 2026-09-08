"""The LittleSis connector proposes more than officers: the org record, each officer's
other seats, and the org's own affiliations. Runs against the committed fixtures with
the cache read-only, so it never touches the network or Neo4j."""
import pytest

from illuminate.connectors import http
from illuminate.connectors.littlesis import LittleSisConnector, _role
from illuminate.ids import entity_id
from illuminate.seed.seed import FIXTURES


@pytest.fixture(autouse=True)
def offline_fixtures():
    http.set_cache_dir(FIXTURES, read_only=True)
    yield
    http.set_cache_dir(None)


def _by_pred(facts):
    out = {}
    for f in facts:
        out.setdefault(f.predicate, []).append(f)
    return out


async def test_raytheon_yields_record_people_seats_and_affiliations():
    name = "RAYTHEON COMPANY"
    facts = await LittleSisConnector().enrich({"id": entity_id(name=name), "name": name}, "local")
    by = _by_pred(facts)
    # the org record
    assert by["attr:littlesis_id"][0].value == "113"
    assert by["attr:ticker"][0].value == "RTN"
    assert by["attr:revenue"][0].value.isdigit()
    assert by["attr:lda_registrant_id"][0].value == "32828"
    assert "Raytheon" in by["attr:aliases_text"][0].value
    assert "Public Company" in by["attr:org_types"][0].value
    # officers and directors, one tenure per edge, plus their seats elsewhere
    roles = by["HELD_ROLE"]
    at_org = [f for f in roles if f.object.id == entity_id(name=name)]
    elsewhere = [f for f in roles if f.object.id != entity_id(name=name)]
    assert at_org and all(f.props["role_type"] in ("board", "executive", "both") for f in at_org)
    assert all(f.merge_keys == ["from", "title"] for f in roles)
    assert elsewhere, "an officer's other seats are followed"
    kinds = {f.object.props.get("kind") for f in elsewhere}
    assert "agency" in kinds, "a government post becomes an agency entity"
    gov = next(f for f in elsewhere if f.object.props.get("kind") == "agency")
    assert gov.object.props.get("org_types") and "Government Body" in gov.object.props["org_types"]
    assert gov.object.props.get("littlesis_id")
    # the org's own ties
    assert by.get("MEMBER_OF"), "memberships are recorded"
    assert by.get("DONATED_TO"), "donations are recorded"
    for f in by.get("MEMBER_OF", []) + by.get("DONATED_TO", []) + by.get("LOBBIES", []) + by.get("TRANSACTS_WITH", []):
        assert f.subject.label == "Entity" and f.object.label == "Entity"
        assert f.artifact and f.artifact.url.startswith("https://littlesis.org/relationships/")
    assert by["attr:board_size"][0].value.isdigit()


async def test_unknown_org_yields_nothing():
    facts = await LittleSisConnector().enrich({"id": "ent_x", "name": "DEFENSE SYSTEMS AND SOLUTIONS"}, "local")
    assert facts == []


def test_role_falls_back_when_flags_are_null():
    title, role_type, frm, to, current = _role({"description1": None, "start_date": "2019-00-00", "end_date": None, "is_current": None, "category_attributes": {"is_board": None, "is_executive": None}})
    assert (title, role_type, frm, to, current) == ("Position", "position", "2019-01-01", None, True)
    title, role_type, *_ = _role({"description1": "Chair", "category_attributes": {"is_board": True, "is_executive": True}})
    assert (title, role_type) == ("Chair", "both")
