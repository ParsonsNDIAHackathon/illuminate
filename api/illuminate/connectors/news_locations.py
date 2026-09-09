"""Conservative headline locality lookup. Coordinates describe towns, not verified incidents."""
import gzip
import json
import re
from functools import lru_cache
from pathlib import Path


def words(text):
    return re.findall(r"[^\W_]+", text.casefold(), re.UNICODE)


@lru_cache(maxsize=1)
def gazetteer():
    with gzip.open(Path(__file__).resolve().parents[1] / 'data/news_places.json.gz', 'rt') as f:
        data = json.load(f)
    index = {}
    for city in data['cities']:
        for name in {city[1], city[2]}:
            key = tuple(words(name))
            if key and len(''.join(key)) >= 4:
                index.setdefault(key, []).append(city)
    context = {}
    for code, name in data['countries'].items():
        context.setdefault(tuple(words(name)), set()).add(code)
    for code, names in data['admins'].items():
        for name in names:
            context.setdefault(tuple(words(name)), set()).add(code)
    for code, names in {'US': ['USA', 'United States', 'U.S.'], 'GB': ['UK', 'Britain', 'United Kingdom']}.items():
        for name in names:
            context.setdefault(tuple(words(name)), set()).add(code)
    return data, index, context


@lru_cache(maxsize=2048)
def headline_locations(title):
    data, index, context = gazetteer()
    tokens = words(title)
    spans = [(start, end, tuple(tokens[start:end])) for start in range(len(tokens))
             for end in range(start + 1, min(len(tokens), start + 6) + 1)]
    contexts = set().union(*(context.get(key, set()) for _, _, key in spans))
    # US postal abbreviations only count when written as uppercase tokens.
    contexts.update('US.' + code for code in re.findall(r'\b[A-Z]{2}\b', title)
                    if 'US.' + code in data['admins'])
    found, occupied = [], set()
    for start, end, key in sorted(spans, key=lambda span: span[1] - span[0], reverse=True):
        if any(i in occupied for i in range(start, end)) or key in context:
            continue  # Never reinterpret a state/country as a namesake town.
        candidates = index.get(key, [])
        regional = [c for c in candidates if c[6] in contexts]
        national = [c for c in candidates if c[5] in contexts]
        candidates = regional or national or candidates
        candidates = {c[0]: c for c in candidates}
        if len(candidates) != 1:
            continue  # No population-based guesses for duplicate town names.
        city = next(iter(candidates.values()))
        if end < len(tokens) and tokens[end] in {'county', 'province', 'state', 'district', 'university'}:
            continue
        cue = start > 0 and tokens[start - 1] in {'in', 'near', 'at', 'outside', 'around'}
        adjacent_context = any(context.get(tuple(tokens[end:stop]), set()) & {city[5], city[6]}
                               for stop in range(end + 1, min(len(tokens), end + 6) + 1))
        if not (cue or adjacent_context):
            continue
        if not contexts and city[7] < 100_000:
            continue  # A small namesake town may be absent from this gazetteer.
        # Explicit geography must agree with the town when it is present.
        if contexts and not (regional or national):
            continue
        admin = data['admins'].get(city[6], [''])[0]
        country = data['countries'].get(city[5], city[5])
        found.append({'code': 'geonames:' + city[0], 'name': ', '.join(filter(None, [city[1], admin, country])),
                      'latitude': city[3], 'longitude': city[4], 'country': city[5],
                      'precision': 'locality', 'source': 'GeoNames',
                      'evidence': ' '.join(tokens[start:end])})
        occupied.update(range(start, end))
    return found


def locate_articles(articles):
    return [{**article, 'locations': headline_locations(article.get('title', ''))} for article in articles]
