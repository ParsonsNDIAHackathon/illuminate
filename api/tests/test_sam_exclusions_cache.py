import csv
import io
import zipfile

import pytest

from illuminate.config import settings
from illuminate.connectors import http
from illuminate.connectors import sam_exclusions


def _extract_zip() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        csv_output = io.StringIO()
        writer = csv.DictWriter(
            csv_output,
            fieldnames=[
                "Classification",
                "Record Status",
                "Name",
                "Unique Entity ID",
                "CAGE",
                "Excluding Agency",
                "Exclusion Type",
                "Exclusion Program",
                "Active Date",
                "Termination Date",
                "Country",
                "SAM Number",
            ],
        )
        writer.writeheader()
        writer.writerow({
            "Classification": "Firm",
            "Record Status": "Active",
            "Name": "Example Supplier",
            "Unique Entity ID": "UEI123",
            "CAGE": "CAGE1",
        })
        archive.writestr("Exclusions.csv", csv_output.getvalue().encode("latin-1"))
    return output.getvalue()


async def test_sam_extract_routes_listing_and_large_zip_through_shared_helpers(
    tmp_path, monkeypatch,
):
    name = "SAM_Exclusions_20260908.ZIP"
    listing_calls = []
    document_calls = []

    async def listing(method, url, **kwargs):
        listing_calls.append((method, url, kwargs))
        return {
            "_embedded": {
                "customS3ObjectSummaryList": [{"displayKey": name}],
            },
        }

    async def document(url, **kwargs):
        document_calls.append((url, kwargs))
        return {
            "url": url,
            "body": _extract_zip(),
            "content_type": "application/zip",
            "retrieved_at": 1_700_000_000.0,
            "truncated": False,
        }

    http.set_cache_dir(tmp_path)
    monkeypatch.setattr(
        sam_exclusions, "_index_paths",
        lambda: [tmp_path / sam_exclusions.INDEX_NAME],
    )
    monkeypatch.setattr(sam_exclusions, "fetch_json", listing)
    monkeypatch.setattr(sam_exclusions, "fetch_document", document)
    monkeypatch.setattr(sam_exclusions, "_index", None)
    monkeypatch.setattr(sam_exclusions, "_index_mode", None)

    result = await sam_exclusions.refresh_index(force=True)

    assert result["extract"] == name
    assert result["rows"][0]["uei"] == "UEI123"
    assert listing_calls[0][2]["source"] == "sam-exclusions"
    assert "listing-2026" in listing_calls[0][2]["contract"]
    assert document_calls == [(
        sam_exclusions.DL_URL.format(name=name),
        {
            "ttl": 3650 * 86400,
            "timeout": 300,
            "max_bytes": sam_exclusions.EXTRACT_MAX_BYTES,
            "source": "sam-exclusions",
            "contract": "sam-exclusions-public-v2-zip-v1",
        },
    )]


async def test_sam_required_cache_outage_never_attempts_zip_download(
    tmp_path, monkeypatch,
):
    attempted = False

    async def unavailable(*_args, **_kwargs):
        raise http.HttpError(0, "shared-cache://unavailable")

    async def document(*_args, **_kwargs):
        nonlocal attempted
        attempted = True
        raise AssertionError("zip download must not bypass listing cache failure")

    http.set_cache_dir(tmp_path)
    monkeypatch.setattr(
        sam_exclusions, "_index_paths",
        lambda: [tmp_path / sam_exclusions.INDEX_NAME],
    )
    monkeypatch.setattr(settings, "illuminate_fetch_cache_required", True)
    monkeypatch.setattr(sam_exclusions, "fetch_json", unavailable)
    monkeypatch.setattr(sam_exclusions, "fetch_document", document)
    monkeypatch.setattr(sam_exclusions, "_index", None)
    monkeypatch.setattr(sam_exclusions, "_index_mode", None)

    with pytest.raises(http.HttpError):
        await sam_exclusions.refresh_index(force=True)
    assert attempted is False