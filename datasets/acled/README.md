# ACLED

Version-controlled snapshots of ACLED aggregated data downloaded from https://acleddata.com/conflict-data/download-data-files.

- [2026-09-09 snapshot](2026-09-09/README.md): 12 original Excel workbooks, with source metadata and SHA-256 checksums in manifest.json.

Data source title: **ACLED**. These files contain aggregate counts rather than individual geolocated events.

The map uses the six regional workbooks, which contain weekly event-type counts
and state/province centroids. The six country summary workbooks overlap this data
and are retained as source material but not added to map totals.

Run `python3 scripts/build_acled_map.py` to regenerate
`web/src/data/acledMap.json` after changing the snapshot. The script verifies source
checksums and reads past the exports' incorrect worksheet dimensions. It uses the
newest regional export for each country (filename order breaks date ties), removes
exact duplicates within that export, and rejects conflicting duplicates within
the chosen export. This prevents differing revisions in overlapping regional
files from being summed. It computes 7-day,
1-month, 3-month, and 1-year views ending at the latest week covered by all six
regions (2026-08-15 for this snapshot). Weekly reporting dates are included when
strictly after the start boundary and on or before the end boundary; events are
not assigned invented daily dates. Each area retains its workbook provenance.

The frontend loads the prepared snapshot once per session, independently of
GDELT. No ACLED account or external API request is required. Markers represent
area centroids and expose event counts, reported fatalities, and event types.
