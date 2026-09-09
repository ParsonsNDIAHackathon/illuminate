# News locality lookup

`news_places.json.gz` is a compact derivative of GeoNames cities500.zip,
admin1CodesASCII.txt and countryInfo.txt downloaded 2026-09-09 from
https://download.geonames.org/export/dump/ (235,694 populated places).

Attribution: GeoNames, https://www.geonames.org/ — Creative Commons Attribution
4.0, https://creativecommons.org/licenses/by/4.0/ . Data is provided without a
warranty of accuracy or completeness. This derivative retains primary/ASCII
names, coordinates, country and first-level administrative divisions.

Rebuild using `scripts/build_news_gazetteer.py` with those three downloaded files.
This is reference geography; news headlines still come from the live news feeds.
No publisher location is used to infer an event. Headline locality matches are
approximate town coordinates, not verified event coordinates. Ambiguous names
fall back to the frontend's broader state/country placement.
