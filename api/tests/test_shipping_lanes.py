import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from fastapi import HTTPException
from illuminate.shipping import EstablishedLanes
from illuminate.routers import shipping


def catalog():
    return json.loads((Path(__file__).parents[1] / 'illuminate/shipping_lanes.json').read_text())


def test_published_lanes_do_not_require_graph_links():
    data = EstablishedLanes.model_validate(catalog())
    assert len(data.lanes) == 7
    assert all(not hasattr(lane, 'relationship_id') for lane in data.lanes)


@pytest.mark.parametrize('issue', ['missing_port', 'duplicate', 'no_source'])
def test_invalid_reference_rejected(issue):
    data = catalog()
    if issue == 'missing_port': data['lanes'][0]['segments'][0]['to_port'] = 'missing'
    elif issue == 'duplicate': data['lanes'].append(data['lanes'][0])
    else: del data['lanes'][0]['source']
    with pytest.raises(ValidationError): EstablishedLanes.model_validate(data)


async def test_override_empty_and_malformed(monkeypatch, tmp_path):
    monkeypatch.setattr(shipping, 'settings', SimpleNamespace(data_dir=tmp_path))
    assert len((await shipping.established_lanes()).lanes) == 7
    override = tmp_path / 'shipping_lanes.json'
    override.write_text('{"ports": [], "lanes": []}')
    assert not (await shipping.established_lanes()).lanes
    override.write_text('{}')
    with pytest.raises(HTTPException) as exc: await shipping.established_lanes()
    assert exc.value.status_code == 503
