# ACLED

Data source title: **ACLED**

Source: https://acleddata.com/conflict-data/download-data-files

Stored on 2026-09-09 from files downloaded by the user. All 12 original Excel workbooks are preserved without modification; originals remain in Downloads.

Contents:

- Six country-level aggregate workbooks: political violence (annual and monthly), demonstrations, civilian targeting, fatalities, and civilian fatalities; filenames indicate 21 August 2026.
- Six regional aggregate workbooks: Africa, Asia-Pacific, Europe and Central Asia, Latin America and the Caribbean, Middle East, and United States and Canada; filenames indicate coverage through the week of 15 or 29 August 2026.

These are aggregated datasets, not individual geolocated event records. The six regional workbooks power the ACLED map layer. See ../README.md for the reproducible map preparation process and aggregation rules.

See manifest.json for source metadata, file sizes, and SHA-256 checksums. Every workbook archive was checked for integrity and each stored copy was verified against its original. This snapshot is stored under datasets/acled/ for version control, separate from private runtime data in api/data/.
