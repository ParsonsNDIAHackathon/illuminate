"""Build the offline map snapshot from ACLED's six regional XLSX files (stdlib only).

Run from any directory: python3 scripts/build_acled_map.py
Country summary files overlap the regional files and must not be added to them.
"""
from pathlib import Path
from datetime import date, timedelta
from calendar import monthrange
import math
import hashlib
import json
import re
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'datasets/acled/2026-09-09'
OUTPUT = ROOT / 'web/src/data/acledMap.json'
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'


def rows(path):
    # Ignore incorrect A1:A1 dimensions in these exports; stream every physical row.
    with zipfile.ZipFile(path) as archive:
        strings = []
        if 'xl/sharedStrings.xml' in archive.namelist():
            strings = [''.join(n.itertext()) for n in ET.fromstring(archive.read('xl/sharedStrings.xml'))]
        with archive.open('xl/worksheets/sheet1.xml') as sheet:
            for _, row in ET.iterparse(sheet, events=('end',)):
                if row.tag != NS + 'row':
                    continue
                values = {}
                for cell in row:
                    column = re.sub(r'\d', '', cell.attrib['r'])
                    value = cell.findtext(NS + 'v')
                    if cell.attrib.get('t') == 's':
                        value = strings[int(value)]
                    elif cell.attrib.get('t') == 'inlineStr':
                        value = ''.join(cell.find(NS + 'is').itertext())
                    values[column] = value
                yield values
                row.clear()


def windows(end):
    def months_ago(n):
        y, m = divmod(end.year * 12 + end.month - 1 - n, 12)
        return date(y, m + 1, min(end.day, monthrange(y, m + 1)[1]))
    return {'7d': end - timedelta(days=7), '1m': months_ago(1),
            '3m': months_ago(3), '12m': months_ago(12)}


def main():
    files = sorted(SOURCE.glob('*_aggregated_data_*.xlsx'))
    assert len(files) == 6, 'Expected exactly six regional workbooks'
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    hashes = {f['filename']: f['sha256'] for f in manifest['files']}
    ends = {p.name: date.fromisoformat(re.search(r'week_of-(\d{4}-\d{2}-\d{2})', p.name)[1]) for p in files}
    files.sort(key=lambda p: (-ends[p.name].toordinal(), p.name))
    end = min(ends.values())
    starts = windows(end)
    places = {}
    totals = {key: [0, 0] for key in starts}
    source_rows = 0
    seen = {}
    duplicates = 0
    country_sources = {}
    overlap_rows = 0
    for index, path in enumerate(files):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[path.name], path.name
        iterator = rows(path)
        header = next(iterator)
        columns = {name: col for col, name in header.items()}
        for row in iterator:
            source_rows += 1
            get = lambda name: row.get(columns[name])
            week = date(1899, 12, 30) + timedelta(days=int(float(get('WEEK'))))
            if not starts['12m'] < week <= end:
                continue
            country = get('COUNTRY')
            # Revisions differ across overlapping exports. Select one country series
            # from the newest file, breaking equal-date ties by filename.
            owner = country_sources.setdefault(country, index)
            if owner != index:
                overlap_rows += 1
                continue
            key = f"{country}:{get('ID')}"
            identity = (key, week, get('EVENT_TYPE'), get('SUB_EVENT_TYPE'), get('DISORDER_TYPE'))
            lat, lon = float(get('CENTROID_LATITUDE') or 'nan'), float(get('CENTROID_LONGITUDE') or 'nan')
            if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
                lat, lon = None, None
            place = places.setdefault(key, dict(id=key, country=get('COUNTRY'), name=get('ADMIN1'),
                latitude=lat, longitude=lon, sources=[], periods={k: {} for k in starts}))
            assert (place['latitude'], place['longitude']) == (lat, lon)
            if index not in place['sources']:
                place['sources'].append(index)
            events, fatalities = int(get('EVENTS')), int(get('FATALITIES'))
            assert events >= 0 and fatalities >= 0
            if identity in seen:
                assert seen[identity] == (events, fatalities, lat, lon), f'Conflicting aggregate: {identity}'
                duplicates += 1
                continue
            seen[identity] = (events, fatalities, lat, lon)
            for period, start in starts.items():
                if week > start:
                    counts = place['periods'][period].setdefault(get('EVENT_TYPE'), [0, 0])
                    counts[0] += events
                    counts[1] += fatalities
                    totals[period][0] += events
                    totals[period][1] += fatalities
        print(f'Read {path.name}', flush=True)
    result = dict(source='ACLED', snapshot='2026-09-09', through=end.isoformat(),
        windows={k: {'after': v.isoformat(), 'through': end.isoformat()} for k, v in starts.items()},
        sources=[{'filename': p.name, 'through': ends[p.name].isoformat(), 'sha256': hashes[p.name]} for p in files],
        sourceRows=source_rows, duplicateRows=duplicates, overlappingRowsExcluded=overlap_rows,
        totals=totals, places=sorted(places.values(), key=lambda p: p['id']))
    OUTPUT.write_text(json.dumps(result, separators=(',', ':'), ensure_ascii=False) + '\n')
    print(f'{len(places)} areas, totals {totals}; {OUTPUT.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
