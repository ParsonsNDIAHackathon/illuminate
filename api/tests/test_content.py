"""Artifact content: payload shapes read as fields, and the HTML sanitiser.

Offline — the fixtures under illuminate/seed are the same responses the seed replays, so
these assert against payloads the app really stores.
"""
from __future__ import annotations

import json
from pathlib import Path

import illuminate
from illuminate.content import _render_html, detect, document, summarize

FIXTURES = Path(illuminate.__file__).parent / "seed" / "fixtures"


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def hit(doc: dict) -> list[dict]:
    return [{"url": doc["url"], "match": "cached response", "body": doc["body"]}]


def fields(out: dict, section: str) -> dict[str, str]:
    for sec in out["sections"]:
        if sec["title"] == section:
            return {f["label"]: f["value"] for f in sec["fields"]}
    raise AssertionError(f"no {section!r} section in {[s['title'] for s in out['sections']]}")


def find_fixture(probe: str) -> dict:
    """First fixture whose payload has the given dotted path — shapes, not file names."""
    for p in sorted(FIXTURES.glob("*.json")):
        doc = json.loads(p.read_text())
        if isinstance(doc.get("body"), dict) and detect(doc["body"]) == probe:
            return doc
    raise AssertionError(f"no fixture of shape {probe}")


def test_award_reads_as_fields():
    doc = find_fixture("usaspending_award")
    out = summarize({"kind": "award", "source": "USAspending", "url": doc["url"]}, hit(doc))
    assert out["shape"] == "usaspending_award"
    assert fields(out, "Award")["Unique ID"].startswith("CONT_")
    assert fields(out, "Recipient")["Name"]
    assert fields(out, "Agency")["Awarding"]
    # The competition verdict is the connector's own rule, so the viewer and the graph agree.
    assert fields(out, "Competition")["Sole source"] in ("yes", "no")


def test_award_money_and_dates_are_formatted():
    doc = find_fixture("usaspending_award")
    out = summarize({"kind": "award"}, hit(doc))
    award = fields(out, "Award")
    assert award["Obligated"].startswith("$") and "," in award["Obligated"]
    assert len(fields(out, "Period of performance")["Start"]) == 10


def test_lei_record_reads_as_fields():
    doc = find_fixture("gleif_lei")
    out = summarize({"kind": "registry", "source": "GLEIF"}, hit(doc))
    assert out["shape"] == "gleif_lei"
    assert len(fields(out, "Entity")["LEI"]) == 20
    assert fields(out, "Registration")["Status"]
    assert fields(out, "Addresses")["Legal address"]


def test_edgar_submissions_read_as_fields():
    doc = find_fixture("edgar_submissions")
    out = summarize({"kind": "filing", "source": "EDGAR"}, hit(doc))
    assert fields(out, "Filer")["CIK"]
    assert fields(out, "Filer")["Name"]


def test_unmapped_payload_still_renders_as_fields():
    """An unknown shape must not fall back to a blob — flattening keeps it readable."""
    body = {"widget": {"name": "Acme", "count": 3, "nested": {"deep": "value"}}, "ok": True}
    out = summarize({"kind": "record"}, [{"url": "https://x.test/", "match": "cached", "body": body}])
    assert out["shape"] is None
    flat = fields(out, "Source payload")
    assert flat["Widget › Name"] == "Acme"
    assert flat["Widget › Nested › Deep"] == "value"
    assert flat["Ok"] == "yes"


def test_node_properties_always_show_including_unknown_ones():
    props = {"id": "art_1", "kind": "news", "source": "GDELT", "url": "https://ex.test/a",
             "domain": "ex.test", "sentiment": "negative", "some_new_prop": "kept"}
    rec = fields(summarize(props, []), "Record")
    assert rec["Kind"] == "news" and rec["Sentiment"] == "negative"
    assert rec["Some new prop"] == "kept"      # unmapped properties are never hidden
    assert "Id" not in rec and "Url" not in rec  # shown in the dialog header instead


def test_urls_become_links():
    out = summarize({"kind": "record"}, [{"url": "https://x.test/", "match": "c",
                                          "body": {"site": "https://example.test/page"}}])
    field = next(f for f in out["sections"][-1]["fields"] if f["label"] == "Site")
    assert field["href"] == "https://example.test/page"


# --- the sanitiser ----------------------------------------------------------------

HOSTILE = """<html><head><title>Form 10-K</title><script>alert(document.cookie)</script>
<style>td[headers="x"]{color:red}</style><link rel=stylesheet href=x.css></head><body onload="steal()">
<ix:header><ix:hidden>0001571123us-gaap:CommonStockMember</ix:hidden></ix:header>
<h1>ANNUAL REPORT</h1><p>Revenue rose to <b>$77.8bn</b>.</p>
<table><tr><th>Year</th><td>2025</td></tr></table>
<a href="javascript:alert(1)">bad</a><a href="/edgar/x.htm">good</a>
<img src="logo.gif" onerror="alert(2)"><iframe src="https://evil.test/"></iframe>
<p>Caf&eacute; &lt;not a tag&gt;</p></body></html>"""


def rendered_body(raw: str, base: str = "https://www.sec.gov/Archives/edgar/data/1/d.htm") -> str:
    return _render_html(raw, base)["html"].split("<body>", 1)[1]


def test_sanitiser_strips_active_content():
    body = rendered_body(HOSTILE).lower()
    for bad in ("<script", "alert(", "onload", "onerror", "<iframe", "<link", "javascript:"):
        assert bad not in body, f"{bad} survived sanitising"


def test_document_stylesheet_survives_unescaped():
    """A filing is unreadable without its CSS, and the frame is sandboxed. But escaping the
    CSS would corrupt every attribute selector in it, so it has to pass through verbatim."""
    body = rendered_body(HOSTILE)
    assert '<style>td[headers="x"]{color:red}</style>' in body


def test_page_chrome_is_kept_in_the_render_but_left_out_of_the_text():
    raw = "<body><nav><a href=/>Menu</a></nav><article><p>The story.</p></article><footer>(c) 2026</footer></body>"
    out = _render_html(raw, "https://news.test/a")
    assert "Menu" in out["html"] and "(c) 2026" in out["html"]
    assert out["text"] == "The story."


def test_inline_xbrl_metadata_is_dropped():
    """ix:hidden is invisible in a browser but is thousands of characters of tag soup in
    any text reading — EDGAR's inline XBRL would otherwise bury the filing."""
    out = _render_html(HOSTILE, "https://www.sec.gov/x")
    assert "us-gaap:CommonStockMember" not in out["text"]
    assert "us-gaap:CommonStockMember" not in out["html"]
    assert out["text"].lstrip().startswith("ANNUAL REPORT")


def test_sanitiser_keeps_the_document():
    body = rendered_body(HOSTILE)
    assert "<table>" in body and "<th>" in body and "<b>" in body
    assert '<img src="logo.gif"' in body     # image kept, its handler dropped
    assert "/edgar/x.htm" in body            # relative link kept for the base tag
    assert "Café" in body                    # entity decoded
    assert "&lt;not a tag&gt;" in body       # text re-escaped, not reinterpreted


def test_void_tag_in_head_does_not_swallow_the_body():
    """<link> and <meta> never close; skipping to their end tag would hide everything."""
    body = rendered_body('<html><head><link rel=x><meta charset=utf-8></head><body><p>kept</p></body></html>')
    assert "kept" in body


def test_render_reports_title_and_reader_text():
    out = _render_html(HOSTILE, "https://www.sec.gov/x")
    assert out["render"] == "html" and out["title"] == "Form 10-K"
    assert "ANNUAL REPORT" in out["text"]
    # Text carries no markup — but a literal "<" that was written as &lt; stays literal.
    for tag in ("<p", "<b>", "<table", "<h1", "<img"):
        assert tag not in out["text"]
    assert "<not a tag>" in out["text"]
    assert "alert" not in out["text"]


def test_base_url_is_escaped_into_the_frame():
    out = _render_html("<p>x</p>", 'https://x.test/a"onload="evil')
    assert 'onload="evil' not in out["html"]


# --- document dispatch ------------------------------------------------------------

async def test_javascript_pages_report_no_document_without_fetching():
    for url in ("https://www.usaspending.gov/award/CONT_AWD_1", "https://www.gleif.org/#/record/X",
                "https://sam.gov/entity/ABC/coreData"):
        out = await document({"url": url})
        assert out["status"] == "unavailable"
        assert "Details tab" in out["note"]


async def test_artifact_without_a_url_reports_it():
    out = await document({"kind": "news"})
    assert out["status"] == "unavailable" and "no source URL" in out["note"]
