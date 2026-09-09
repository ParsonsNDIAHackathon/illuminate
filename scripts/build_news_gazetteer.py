"""Build the bundled GeoNames lookup from downloaded cities500.zip,
admin1CodesASCII.txt and countryInfo.txt. Usage: python scripts/build_news_gazetteer.py
<archive> <admin1 file> <country file>. Source: https://download.geonames.org/export/dump/
GeoNames CC BY 4.0; only primary and ASCII city names retained.
"""
import gzip
import json
from pathlib import Path
import sys
import zipfile

archive, admin_path, country_path = sys.argv[1:]
admins = {p[0]: p[1:3] for line in Path(admin_path).read_text().splitlines() if (p := line.split('\t')) and len(p) >= 3}
countries = {p[0]: p[4] for line in Path(country_path).read_text().splitlines() if not line.startswith('#') and len(p := line.split('\t')) > 4}
with zipfile.ZipFile(archive) as z:
    cities = []
    for line in z.read('cities500.txt').decode().splitlines():
        p = line.split('\t')
        cities.append([p[0], p[1], p[2], float(p[4]), float(p[5]), p[8], p[8] + '.' + p[10], int(p[14])])
output = Path(__file__).resolve().parents[1] / 'api/illuminate/data/news_places.json.gz'
with output.open('wb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as f:
    f.write(json.dumps({'countries': countries, 'admins': admins, 'cities': cities}, ensure_ascii=False, separators=(',', ':')).encode())
print(f'{len(cities)} cities, {output.stat().st_size} bytes')
