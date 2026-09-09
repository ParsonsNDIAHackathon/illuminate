import copy
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from illuminate.shipping import ShippingCatalog
from illuminate.routers import shipping


def demo():
    return json.loads((Path(__file__).parents[1] / 'illuminate/shipping_demo.json').read_text())


def test_demo_is_explicitly_illustrative():
    catalog = ShippingCatalog.model_validate(demo())
    assert len(catalog.routes) == 2
    assert all(r.status == 'illustrative' and r.source.reference and r.notes for r in catalog.routes)


@pytest.mark.parametrize('change', ['unknown_port', 'latitude', 'duplicate_route', 'status', 'missing_source', 'discontinuous', 'future_date'])
def test_invalid_routes_rejected(change):
    data = demo()
    if change == 'unknown_port': data['routes'][0]['segments'][0]['to_port'] = 'missing'
    elif change == 'latitude': data['ports'][0]['latitude'] = 91
    elif change == 'duplicate_route': data['routes'].append(copy.deepcopy(data['routes'][0]))
    elif change == 'status': data['routes'][0]['status'] = 'probably'
    elif change == 'missing_source': del data['routes'][0]['source']
    elif change == 'discontinuous': data['routes'][0]['segments'] *= 2
    elif change == 'future_date': data['routes'][0]['updated_at'] = str(date.today() + timedelta(days=1))
    with pytest.raises(ValidationError): ShippingCatalog.model_validate(data)


async def test_catalog_override_and_invalid_file(monkeypatch, tmp_path):
    monkeypatch.setattr(shipping, 'settings', SimpleNamespace(data_dir=tmp_path))
    assert len((await shipping.shipping_catalog()).routes) == 2
    path = tmp_path / 'shipping.json'
    path.write_text('{"ports":[],"routes":[]}')
    assert (await shipping.shipping_catalog()).routes == []
    path.write_text('{bad data')
    with pytest.raises(HTTPException) as error:
        await shipping.shipping_catalog()
    assert error.value.status_code == 503
