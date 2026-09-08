"""How a person's role at a flagged entity is graded.

The vendor's own record is clean; the exposure is only reachable through the person, so the
severity turns on whether that second role is *current*. Ported alongside the scenario seed in
`test_scenario_insider.py`, which covers what the seed writes rather than how it is scored.
"""
from __future__ import annotations

import pytest

from illuminate.report import risk_indicators


def core() -> dict:
    return {"e": {"id": "vendor", "name": "Vendor"}, "parent_seat": None, "ultimate_parents": []}


def _person_at_flagged(*, other_current: bool, person_current: bool = True) -> dict:
    person = {
        "person_id": "person", "edge_id": "role-edge", "claim_id": None,
        "name": "R. Ostrowski", "title": "Network Operations Engineer",
        "source": "scenario", "source_url": None, "simulated": False,
        "interlock": False, "formerly_elsewhere": False,
        "current": person_current,
        "elsewhere": [{
            "entity_id": "threat-group", "entity": "Obsidian Lantern",
            "role_edge_id": "affiliation-edge", "current": other_current,
            "flagged": True, "simulated": False, "supplier": False,
            "source_url": "https://example.test/threat-group",
        }],
    }
    person["moved_to_flagged"] = other_current and not person_current
    key = "current" if person_current else "former"
    return {"current": [], "former": [], key: [person]}


@pytest.mark.asyncio
async def test_a_current_employee_concurrently_inside_a_flagged_entity_is_a_high_finding():
    # The employer's own record is clean; the exposure is only reachable through the person.
    ppl = _person_at_flagged(other_current=True)
    risk = await risk_indicators("vendor", core(), {"supplies": []}, ppl, [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "people")
    assert indicator["severity"] == "high"
    assert "concurrently at flagged entity" in indicator["label"]
    assert "Obsidian Lantern" in indicator["label"]
    assert indicator["element_ids"] == ["person", "role-edge", "threat-group", "affiliation-edge"]


@pytest.mark.asyncio
async def test_a_lapsed_role_at_a_flagged_entity_stays_medium():
    ppl = _person_at_flagged(other_current=False)
    risk = await risk_indicators("vendor", core(), {"supplies": []}, ppl, [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "people")
    assert indicator["severity"] == "medium"
    assert "linked to flagged entity" in indicator["label"]


@pytest.mark.asyncio
async def test_a_former_employee_who_moved_to_a_flagged_entity_stays_medium():
    ppl = _person_at_flagged(other_current=True, person_current=False)
    risk = await risk_indicators("vendor", core(), {"supplies": []}, ppl, [])
    indicator = next(i for i in risk["indicators"] if i["family"] == "people")
    assert indicator["severity"] == "medium"
    assert indicator["label"].startswith("Former")
