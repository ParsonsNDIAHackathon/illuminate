"""Sanctions screening against the UN Consolidated List and the OFAC SDN.

Both lists are pinned to small inline samples in the real published shape; no test in
this module reaches the network.
"""
from __future__ import annotations

import pytest

from illuminate.connectors import ofac, un_sanctions
from illuminate.connectors.registry import connector_names, get_connector

UN_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<CONSOLIDATED_LIST dateGenerated="2026-09-07T23:00:04.871Z">
  <INDIVIDUALS>
    <INDIVIDUAL>
      <DATAID>6907993</DATAID>
      <FIRST_NAME>ERIC</FIRST_NAME>
      <SECOND_NAME>BADEGE</SECOND_NAME>
      <UN_LIST_TYPE>DRC</UN_LIST_TYPE>
      <REFERENCE_NUMBER>CDi.001</REFERENCE_NUMBER>
      <LISTED_ON>2012-12-31</LISTED_ON>
      <NATIONALITY><VALUE>Democratic Republic of the Congo</VALUE></NATIONALITY>
      <INDIVIDUAL_ALIAS><QUALITY/><ALIAS_NAME/></INDIVIDUAL_ALIAS>
    </INDIVIDUAL>
  </INDIVIDUALS>
  <ENTITIES>
    <ENTITY>
      <DATAID>6908402</DATAID>
      <FIRST_NAME>ADF</FIRST_NAME>
      <UN_LIST_TYPE>DRC</UN_LIST_TYPE>
      <REFERENCE_NUMBER>CDe.001</REFERENCE_NUMBER>
      <LISTED_ON>2014-06-30</LISTED_ON>
      <ENTITY_ALIAS><QUALITY>Good</QUALITY><ALIAS_NAME>Allied Democratic Forces</ALIAS_NAME></ENTITY_ALIAS>
      <ENTITY_ALIAS><QUALITY>Good</QUALITY><ALIAS_NAME>ADF/NALU</ALIAS_NAME></ENTITY_ALIAS>
    </ENTITY>
  </ENTITIES>
</CONSOLIDATED_LIST>"""

# ent_num, name, type, program, ... remarks at index 11
SDN_CSV = (
    '1,"HAMMER ENTERPRISES LTD","-0-","CYBER2",,,,,,,,"remarks"\n'
    '2,"DELACROIX, Marcus Whitfield","individual","CYBER2",,,,,,,,"remarks"\n'
    '3,"BADEGE, Eric","individual","DRC",,,,,,,,"remarks"\n'
)


@pytest.fixture
def listing():
    return un_sanctions.parse(UN_XML)


def test_the_parser_keeps_both_sections_and_the_generation_stamp(listing):
    assert listing["generated"] == "2026-09-07T23:00:04.871Z"
    assert len(listing["entities"]) == 1 and len(listing["individuals"]) == 1
    entity = listing["entities"][0]
    assert entity["reference"] == "CDe.001" and entity["regime"] == "DRC"
    assert entity["aliases"] == ["Allied Democratic Forces", "ADF/NALU"]
    # An individual's name is split over the name fields and has to be rejoined.
    assert listing["individuals"][0]["name"] == "ERIC BADEGE"
    assert listing["individuals"][0]["nationality"] == "Democratic Republic of the Congo"


def test_an_empty_alias_element_is_not_read_as_a_name(listing):
    # The published XML pads records with <ALIAS_NAME/>; screening on "" would match all.
    assert listing["individuals"][0]["aliases"] == []


def test_a_designated_entity_is_found_through_its_alias(listing):
    res = un_sanctions.screen("Allied Democratic Forces", listing=listing)
    assert res["result"] == "hit"
    assert res["hits"][0]["reference"] == "CDe.001"
    assert "CDe.001" in un_sanctions.describe(res, "entity designations")


def test_an_ordinary_supplier_screens_clear_and_the_detail_says_what_was_searched(listing):
    res = un_sanctions.screen("Hamilton Sundstrand Corporation", listing=listing)
    assert res["result"] == "clear"
    detail = un_sanctions.describe(res, "entity designations")
    assert "no match against 1" in detail and "2026-09-07" in detail


def test_a_designated_individual_is_found_by_full_name(listing):
    assert un_sanctions.screen_person("Eric Badege", listing=listing)["result"] == "hit"
    # Reordered given/family name is the same person.
    assert un_sanctions.screen_person("Badege, Eric", listing=listing)["result"] == "hit"


def test_a_single_token_never_matches_a_person(listing):
    # "Badege" alone would sweep in every namesake; a screen that noisy is worse than none.
    assert un_sanctions.screen_person("Badege", listing=listing)["result"] == "clear"
    assert un_sanctions.screen_person("R. Ostrowski", listing=listing)["result"] == "clear"


def test_people_are_screened_against_people_and_organisations_against_organisations(listing):
    # The individual is not reachable from the entity screen, nor the entity from the person one.
    assert un_sanctions.screen("Eric Badege", listing=listing)["result"] == "clear"
    assert un_sanctions.screen_person("Allied Democratic Forces", listing=listing)["result"] == "clear"


def test_the_un_connector_is_registered_with_authoritative_trust():
    assert "un_sanctions" in connector_names()
    conn = get_connector("un_sanctions")
    assert conn.trust == "authoritative" and conn.needs_key() is False


@pytest.fixture
def sdn(monkeypatch):
    async def rows():
        return await _rows()

    async def _rows():
        import csv
        import io
        out = []
        for r in csv.reader(io.StringIO(SDN_CSV)):
            out.append({"ent_num": r[0], "name": r[1], "type": r[2].strip(), "program": r[3].strip(), "remarks": r[11].strip()})
        return out

    monkeypatch.setattr(ofac, "sdn_rows", rows)


@pytest.mark.asyncio
async def test_ofac_screens_individuals_without_disturbing_the_organisation_screen(sdn):
    person = await ofac.screen_person("Marcus Whitfield Delacroix")
    assert person["result"] == "hit"
    assert person["hits"][0]["program"] == "CYBER2"
    # The organisation screen still ignores the individual rows entirely.
    org = await ofac.screen_name("Marcus Whitfield Delacroix")
    assert org["result"] == "clear"
    assert (await ofac.screen_name("Hammer Enterprises Ltd"))["result"] == "hit"


@pytest.mark.asyncio
async def test_ofac_person_screen_ignores_the_organisation_rows(sdn):
    assert (await ofac.screen_person("Hammer Enterprises Ltd"))["result"] == "clear"


@pytest.mark.asyncio
async def test_ofac_person_screen_needs_more_than_one_token(sdn):
    assert (await ofac.screen_person("Delacroix"))["result"] == "clear"
