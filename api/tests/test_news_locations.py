from illuminate.connectors.news_locations import headline_locations


def test_local_town_uses_headline_state_context():
    places = headline_locations('Earthquake near Silver Spring, Maryland')
    assert len(places) == 1
    assert 'Silver Spring' in places[0]['name']
    assert abs(places[0]['latitude'] - 38.99) < .1
    assert places[0]['precision'] == 'locality'


def test_duplicate_city_requires_context():
    assert headline_locations('Flood in Springfield') == []
    places = headline_locations('Flood in Springfield, Illinois')
    assert len(places) == 1
    assert 'Illinois' in places[0]['name']


def test_state_only_and_non_location_words_do_not_become_towns():
    assert headline_locations('Maryland earthquake response') == []
    assert headline_locations('Officials Hope for better flood relief') == []
    assert headline_locations('Flood in Paris, Texas')[0]['country'] == 'US'


def test_abbreviated_state_and_conflicting_context():
    assert 'Maryland' in headline_locations('Earthquake near Silver Spring, MD')[0]['name']
    assert headline_locations('Earthquake near Silver Spring, Japan') == []


def test_people_counties_and_context_free_small_towns_are_not_city_events():
    assert headline_locations('Britain showing leadership, says Burnham') == []
    assert headline_locations('Earthquake recorded in Cecil County') == []
    assert headline_locations('Water tanks in College Hill') == []
    assert headline_locations('Flood in Santa Barbara County, California') == []
