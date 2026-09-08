"""What is inside an Artifact, read by content type.

An Artifact node is a pointer — url, title, kind, source — and never the document itself
(schema.py: "Never a raw blob"). So "open the artifact" means one of two things, and this
module provides both:

1. `summarize()` reads the cached source payload that raw.py finds and presents it as
   fields rather than JSON. Each payload shape has a field map: an award record shows
   recipient, competition and period of performance; an LEI record shows legal name,
   jurisdiction and registration status. A shape with no map falls back to flattening its
   scalars, so every artifact renders as a table of fields rather than a blob.

2. `document()` fetches the source document itself and dispatches on its content type:
   HTML is sanitised for a sandboxed frame and also reduced to plain text, PDFs and images
   are proxied as bytes, text and JSON come back as they are. Some source pages are
   JavaScript applications holding nothing to fetch (an award page, an LEI record); for
   those the payload from (1) is the document, and we say so rather than showing an empty
   frame.
"""
from __future__ import annotations

import html as htmllib
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser

import httpx

from .config import settings
from .connectors.http import HttpError, fetch_document
from .connectors.usaspending import is_sole_source

MAX_HTML = 400_000
MAX_TEXT = 80_000
FRAME_TTL = 6 * 3600

# Source pages that are a JavaScript shell — fetching them yields no document.
NO_DOCUMENT = {
    "usaspending.gov": "The USAspending award page renders in the browser, so there is no document to fetch. The award record on the Details tab is the document — it is the response this artifact was recorded from.",
    "gleif.org": "The GLEIF record page renders in the browser, so there is no document to fetch. The LEI record on the Details tab is the document — it is the response this artifact was recorded from.",
    "sam.gov": "SAM.gov renders in the browser and refuses server-side fetches. The registration on the Details tab is the record.",
    "finnhub.io": "A quote is an API value rather than a page. The record on the Details tab is the document.",
}

# Whether a page lets itself be embedded, remembered per URL: X-Frame-Options and CSP
# frame-ancestors are enforced by the browser, which reports nothing back to the page, so a
# refusing site is a blank frame the UI cannot detect. Asking here is the only way to know.
# Kept per URL rather than per host because the two differ — sam.gov refuses its front page
# and allows an entity page.
_frame_seen: dict[str, tuple[bool, float]] = {}


async def frameable(url: str) -> bool:
    """Can a browser embed this page? Conservative: a policy we cannot read as open is a no."""
    seen = _frame_seen.get(url)
    if seen and time.time() - seen[1] < FRAME_TTL:
        return seen[0]
    ok = False
    try:
        hdrs = {"User-Agent": settings.illuminate_user_agent, "Accept": "text/html,*/*"}
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # Streamed so only the headers cross the wire; some hosts refuse HEAD outright.
            async with client.stream("GET", url, headers=hdrs) as r:
                xfo = (r.headers.get("x-frame-options") or "").lower()
                csp = (r.headers.get("content-security-policy") or "").lower()
                anc = re.search(r"frame-ancestors([^;]*)", csp)
                ok = (r.status_code < 400
                      and "deny" not in xfo and "sameorigin" not in xfo
                      and (anc is None or "*" in anc.group(1)))
    except Exception:  # unreachable, TLS, DNS — nothing to frame either way
        ok = False
    _frame_seen[url] = (ok, time.time())
    return ok


# --- paths and formatting ---------------------------------------------------------

def _get(body, path: str):
    """Dotted lookup; a numeric segment indexes a list."""
    cur = body
    for seg in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list):
            if not seg.isdigit() or int(seg) >= len(cur):
                return None
            cur = cur[int(seg)]
        elif isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


def _money(v):
    try:
        return "$" + f"{float(v):,.0f}"
    except (TypeError, ValueError):
        return None


def _date(v):
    s = str(v or "")
    return s[:10] if len(s) >= 10 else (s or None)


def _list(v):
    if not isinstance(v, list) or not v:
        return None
    return ", ".join(str(x) for x in v[:12]) + (f" (+{len(v) - 12} more)" if len(v) > 12 else "")


def _addr(v):
    """USAspending location block."""
    if not isinstance(v, dict):
        return None
    parts = [v.get("address_line1"), v.get("city_name"), v.get("state_code") or v.get("state_name"),
             v.get("zip5"), v.get("country_name") if v.get("location_country_code") != "USA" else None]
    return ", ".join(str(p) for p in parts if p) or None


def _gleif_addr(v):
    if not isinstance(v, dict):
        return None
    parts = list(v.get("addressLines") or []) + [v.get("city"), v.get("region"), v.get("postalCode"), v.get("country")]
    return ", ".join(str(p) for p in parts if p) or None


def _sec_addr(v):
    if not isinstance(v, dict):
        return None
    parts = [v.get("street1"), v.get("street2"), v.get("city"), v.get("stateOrCountry"), v.get("zipCode")]
    return ", ".join(str(p) for p in parts if p) or None


def _names(v):
    """GLEIF otherNames / transliterations: [{name, language}]."""
    if not isinstance(v, list) or not v:
        return None
    return ", ".join(str(x.get("name")) for x in v[:6] if isinstance(x, dict) and x.get("name")) or None


FORMAT = {"money": _money, "date": _date, "list": _list, "addr": _addr, "gleif_addr": _gleif_addr,
          "sec_addr": _sec_addr, "names": _names}


# --- payload shapes ---------------------------------------------------------------
# (label, dotted path, formatter key or None). A field whose value is missing is dropped,
# so a sparse record simply shows fewer rows.

SHAPES: dict[str, list[tuple[str, list[tuple[str, str, str | None]]]]] = {
    "usaspending_award": [
        ("Award", [
            ("Award ID", "piid", None),
            ("Unique ID", "generated_unique_award_id", None),
            ("Type", "type_description", None),
            ("Category", "category", None),
            ("Description", "description", None),
            ("Obligated", "total_obligation", "money"),
            ("Base + all options", "base_and_all_options", "money"),
            ("Signed", "date_signed", "date"),
            ("Sub-awards", "subaward_count", None),
            ("Sub-award total", "total_subaward_amount", "money"),
        ]),
        ("Recipient", [
            ("Name", "recipient.recipient_name", None),
            ("UEI", "recipient.recipient_uei", None),
            ("Parent", "recipient.parent_recipient_name", None),
            ("Parent UEI", "recipient.parent_recipient_uei", None),
            ("Address", "recipient.location", "addr"),
            ("Business types", "recipient.business_categories", "list"),
        ]),
        ("Agency", [
            ("Awarding", "awarding_agency.toptier_agency.name", None),
            ("Awarding sub-agency", "awarding_agency.subtier_agency.name", None),
            ("Awarding office", "awarding_agency.office_agency_name", None),
            ("Funding", "funding_agency.toptier_agency.name", None),
            ("Funding sub-agency", "funding_agency.subtier_agency.name", None),
            ("Parent IDV", "parent_award.piid", None),
            ("IDV type", "parent_award.type_of_idc_description", None),
        ]),
        ("Period of performance", [
            ("Start", "period_of_performance.start_date", "date"),
            ("End", "period_of_performance.end_date", "date"),
            ("Potential end", "period_of_performance.potential_end_date", "date"),
            ("Last modified", "period_of_performance.last_modified_date", "date"),
            ("Place of performance", "place_of_performance", "addr"),
        ]),
        ("Competition", [
            ("Extent competed", "latest_transaction_contract_data.extent_competed_description", None),
            ("Solicitation procedures", "latest_transaction_contract_data.solicitation_procedures_description", None),
            ("Other than full and open", "latest_transaction_contract_data.other_than_full_and_open_description", None),
            ("Offers received", "latest_transaction_contract_data.number_of_offers_received", None),
            ("Set-aside", "latest_transaction_contract_data.type_set_aside_description", None),
            ("Contract pricing", "latest_transaction_contract_data.type_of_contract_pricing", None),
            ("Subcontracting plan", "latest_transaction_contract_data.subcontracting_plan", None),
            ("Commercial item", "latest_transaction_contract_data.commercial_item_acquisition_description", None),
        ]),
        ("Classification", [
            ("PSC", "psc_hierarchy.base_code.code", None),
            ("PSC description", "psc_hierarchy.base_code.description", None),
            ("PSC group", "psc_hierarchy.midtier_code.description", None),
            ("NAICS", "naics_hierarchy.base_code.code", None),
            ("NAICS description", "naics_hierarchy.base_code.description", None),
        ]),
    ],
    "usaspending_recipient": [
        ("Recipient", [
            ("Name", "name", None),
            ("UEI", "uei", None),
            ("Level", "recipient_level", None),
            ("Parent", "parent_name", None),
            ("Parent UEI", "parent_uei", None),
            ("Total awarded", "total_prime_amount", "money"),
            ("Prime awards", "total_prime_awards", None),
            ("Business types", "business_types", "list"),
            ("Address", "location", "addr"),
        ]),
    ],
    "gleif_lei": [
        ("Entity", [
            ("LEI", "data.attributes.lei", None),
            ("Legal name", "data.attributes.entity.legalName.name", None),
            ("Other names", "data.attributes.entity.otherNames", "names"),
            ("Jurisdiction", "data.attributes.entity.jurisdiction", None),
            ("Legal form", "data.attributes.entity.legalForm.id", None),
            ("Category", "data.attributes.entity.category", None),
            ("Status", "data.attributes.entity.status", None),
            ("Registered as", "data.attributes.entity.registeredAs", None),
            ("Created", "data.attributes.entity.creationDate", "date"),
            ("Successor", "data.attributes.entity.successorEntity.name", None),
        ]),
        ("Addresses", [
            ("Legal address", "data.attributes.entity.legalAddress", "gleif_addr"),
            ("Headquarters", "data.attributes.entity.headquartersAddress", "gleif_addr"),
        ]),
        ("Registration", [
            ("Status", "data.attributes.registration.status", None),
            ("First registered", "data.attributes.registration.initialRegistrationDate", "date"),
            ("Last updated", "data.attributes.registration.lastUpdateDate", "date"),
            ("Next renewal", "data.attributes.registration.nextRenewalDate", "date"),
            ("Corroboration", "data.attributes.registration.corroborationLevel", None),
            ("Managing LOU", "data.attributes.registration.managingLou", None),
            ("Conformity", "data.attributes.conformityFlag", None),
        ]),
    ],
    "sam_entity": [
        ("Registration", [
            ("Legal business name", "entityRegistration.legalBusinessName", None),
            ("DBA name", "entityRegistration.dbaName", None),
            ("UEI", "entityRegistration.ueiSAM", None),
            ("CAGE", "entityRegistration.cageCode", None),
            ("Status", "entityRegistration.registrationStatus", None),
            ("Purpose", "entityRegistration.purposeOfRegistrationDesc", None),
            ("Registered", "entityRegistration.registrationDate", "date"),
            ("Expires", "entityRegistration.registrationExpirationDate", "date"),
            ("Last updated", "entityRegistration.lastUpdateDate", "date"),
            ("Activation", "entityRegistration.activationDate", "date"),
        ]),
        ("Core data", [
            ("Entity structure", "coreData.generalInformation.entityStructureDesc", None),
            ("Organization start", "coreData.generalInformation.entityStartDate", "date"),
            ("State of incorporation", "coreData.generalInformation.stateOfIncorporationCode", None),
            ("Country of incorporation", "coreData.generalInformation.countryOfIncorporationCode", None),
            ("Business types", "coreData.businessTypes.businessTypeList", "list"),
        ]),
    ],
    "edgar_submissions": [
        ("Filer", [
            ("Name", "name", None),
            ("CIK", "cik", None),
            ("Entity type", "entityType", None),
            ("SIC", "sic", None),
            ("Industry", "sicDescription", None),
            ("Tickers", "tickers", "list"),
            ("Exchanges", "exchanges", "list"),
            ("State of incorporation", "stateOfIncorporation", None),
            ("EIN", "ein", None),
            ("LEI", "lei", None),
            ("Filer category", "category", None),
            ("Fiscal year end", "fiscalYearEnd", None),
            ("Phone", "phone", None),
            ("Business address", "addresses.business", "sec_addr"),
        ]),
    ],
    "edgar_filing": [
        ("Filing", [
            ("Form", "form", None),
            ("Filed", "filingDate", "date"),
            ("Period", "reportDate", "date"),
            ("Accepted", "acceptanceDateTime", "date"),
            ("Accession", "accessionNumber", None),
            ("Primary document", "primaryDocument", None),
            ("Description", "primaryDocDescription", None),
            ("Items", "items", None),
            ("File number", "fileNumber", None),
            ("Size", "size", None),
        ]),
    ],
    "littlesis_entity": [
        ("Entity", [
            ("Name", "data.attributes.name", None),
            ("Type", "data.attributes.primary_ext", None),
            ("Blurb", "data.attributes.blurb", None),
            ("Summary", "data.attributes.summary", None),
            ("Website", "data.attributes.website", None),
            ("Aliases", "data.attributes.aliases", "list"),
            ("Types", "data.attributes.types", "list"),
            ("Start", "data.attributes.start_date", "date"),
            ("End", "data.attributes.end_date", "date"),
            ("Updated", "data.attributes.updated_at", "date"),
            ("Page", "data.links.self", None),
        ]),
    ],
    "littlesis_relationship": [
        ("Relationship", [
            ("Description", "data.attributes.description", None),
            ("Entity", "data.attributes.entity.name", None),
            ("Related", "data.attributes.related.name", None),
            ("Category", "data.attributes.category_id", None),
            ("Title", "data.attributes.extensions.Position.title", None),
            ("Board member", "data.attributes.extensions.Position.is_board", None),
            ("Executive", "data.attributes.extensions.Position.is_executive", None),
            ("Start", "data.attributes.start_date", "date"),
            ("End", "data.attributes.end_date", "date"),
            ("Current", "data.attributes.is_current", None),
            ("Page", "data.links.self", None),
        ]),
    ],
}

# How a payload announces its shape: (shape name, a path only that shape has).
DETECT: list[tuple[str, str]] = [
    ("usaspending_award", "generated_unique_award_id"),
    ("usaspending_recipient", "recipient_level"),
    ("gleif_lei", "data.attributes.lei"),
    ("sam_entity", "entityRegistration.ueiSAM"),
    ("edgar_submissions", "filings.recent.accessionNumber"),
    ("edgar_filing", "primaryDocument"),
    ("littlesis_relationship", "data.attributes.related"),
    ("littlesis_entity", "data.attributes.primary_ext"),
]

SHAPE_LABEL = {
    "usaspending_award": "USAspending award record",
    "usaspending_recipient": "USAspending recipient record",
    "gleif_lei": "GLEIF LEI record",
    "sam_entity": "SAM.gov registration",
    "edgar_submissions": "EDGAR filer submissions",
    "edgar_filing": "EDGAR filing index row",
    "littlesis_entity": "LittleSis entity",
    "littlesis_relationship": "LittleSis relationship",
}


def detect(body) -> str | None:
    if not isinstance(body, dict):
        return None
    for name, probe in DETECT:
        if _get(body, probe) is not None:
            return name
    return None


# --- node properties --------------------------------------------------------------
# The Artifact node's own fields, named. Anything not listed still shows, under Other, so
# a property a connector adds later is never silently dropped.

PROP_LABELS: list[tuple[str, str, str | None]] = [
    ("Kind", "kind", None), ("Source", "source", None), ("Published", "published_at", "date"),
    ("Retrieved", "retrieved_at", "date"), ("Amount", "amount", "money"), ("Award ID", "award_id", None),
    ("Agency", "agency", None), ("PSC", "psc", None), ("NAICS", "naics", None), ("Form", "form", None),
    ("Domain", "domain", None), ("Language", "language", None), ("Source country", "sourcecountry", None),
    ("Sentiment", "sentiment", None), ("Registration status", "registration_status", None),
    ("Expires", "expires", "date"), ("Quote", "quote", None),
]
PROP_SKIP = {"id", "title", "url"} | {k for _, k, _ in PROP_LABELS}


def _humanize(key: str) -> str:
    return key.replace("_", " ").strip().capitalize()


def _field(label: str, value) -> dict | None:
    if value is None or value == "" or value == [] or value == {}:
        return None
    if isinstance(value, bool):
        value = "yes" if value else "no"
    if isinstance(value, (dict, list)):
        value = json.dumps(value, default=str)[:400]
    s = str(value)
    if len(s) > 4000:
        s = s[:4000] + " …"
    f: dict = {"label": label, "value": s}
    if s.startswith(("http://", "https://")) and " " not in s:
        f["href"] = s
    return f


def _section(title: str, fields: list[dict | None], note: str | None = None) -> dict | None:
    kept = [f for f in fields if f]
    return {"title": title, "fields": kept, **({"note": note} if note else {})} if kept else None


def _mapped(body, spec) -> list[dict]:
    out = []
    for title, rows in spec:
        fields = []
        for label, path, fmt in rows:
            raw = _get(body, path)
            value = FORMAT[fmt](raw) if fmt and raw is not None else raw
            fields.append(_field(label, value))
        if s := _section(title, fields):
            out.append(s)
    return out


def _flatten(body, prefix: str = "", depth: int = 0) -> list[dict]:
    """Fallback for an unmapped payload: every scalar as a field, shallowest first."""
    out: list[dict] = []
    if isinstance(body, dict):
        items = list(body.items())
    elif isinstance(body, list):
        items = [(str(i), v) for i, v in enumerate(body[:20])]
    else:
        return out
    nested = []
    for k, v in items:
        label = _humanize(k) if not prefix else f"{prefix} › {_humanize(k)}"
        if isinstance(v, (dict, list)):
            if depth < 2:
                nested.append((label, v))
            elif f := _field(label, v):
                out.append(f)
        elif f := _field(label, v):
            out.append(f)
    for label, v in nested:
        out.extend(_flatten(v, label, depth + 1))
    return out[:120]


def summarize(props: dict, raw: list[dict]) -> dict:
    """Node properties plus the best cached payload, as titled sections of fields."""
    sections: list[dict] = []
    named = [_field(label, FORMAT[fmt](props.get(key)) if fmt and props.get(key) is not None else props.get(key))
             for label, key, fmt in PROP_LABELS]
    other = [_field(_humanize(k), v) for k, v in sorted(props.items())
             if k not in PROP_SKIP and not isinstance(v, (dict, list))]
    if s := _section("Record", named + other):
        sections.append(s)

    body = raw[0]["body"] if raw else None
    shape = detect(body)
    if body is not None:
        label = SHAPE_LABEL.get(shape or "", "Source payload")
        if shape and shape in SHAPES:
            payload = _mapped(body, SHAPES[shape])
            if shape == "usaspending_award":
                sole, why = is_sole_source(body)
                for sec in payload:
                    if sec["title"] == "Competition":
                        sec["fields"].insert(0, {"label": "Sole source", "value": "yes" if sole else "no",
                                                 "emphasis": "warn" if sole else None})
                        if why:
                            sec["note"] = why
        else:
            payload = [s for s in [_section(label, _flatten(body))] if s]
        if payload:
            payload[0]["source_note"] = f"{label} · {raw[0].get('match', '')}".strip(" ·")
            sections.extend(payload)
    return {"shape": shape, "sections": sections}


# --- the source document ----------------------------------------------------------

BLOCK = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6", "table", "section", "article", "hr", "td", "th"}
# ix:header and ix:hidden carry a filing's inline-XBRL metadata: invisible in a browser,
# but thousands of characters of tag soup in any text reading of the document.
DROP = {"script", "noscript", "iframe", "object", "embed", "applet", "form", "input",
        "button", "select", "textarea", "link", "meta", "base", "svg", "canvas", "audio", "video",
        "source", "track", "template", "ix:header", "ix:hidden"}
VOID = {"area", "br", "col", "hr", "img", "wbr"}
# Page furniture: kept in the rendered markup, left out of the text reading, where a news
# article would otherwise open with two screens of site menu.
CHROME = {"nav", "header", "footer", "aside"}
# Dropped tags that are void: they never produce an end tag, so skipping "until close"
# would swallow the rest of the document — a <link> in the head would hide the body.
DROP_VOID = {"link", "meta", "base", "input", "source", "track"}
SAFE_URL = re.compile(r"^(https?:|mailto:|#|/|\.|[^:]*$|data:image/)", re.I)


class _Html(HTMLParser):
    """Reconstructs the document twice over: sanitised markup for a sandboxed frame, and
    plain text for reading. Scripts, frames and event handlers never survive.

    The document's own <style> does survive: a filing is unreadable without its stylesheet,
    and the frame that renders this runs with sandbox="" — no scripts, no same origin — so
    CSS can do no more than the <img> tags already kept.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.words: list[str] = []
        self.title = ""
        self._skip = 0
        self._chrome = 0
        self._in_title = False
        self._in_style = False

    def _attrs(self, attrs) -> str:
        keep = []
        for k, v in attrs:
            k = (k or "").lower()
            if k.startswith("on") or k in ("srcset", "formaction"):
                continue
            if v is None:
                keep.append(k)
                continue
            if k in ("href", "src", "action") and not SAFE_URL.match(v.strip()):
                continue
            keep.append(f'{k}="{htmllib.escape(v, quote=True)}"')
        return (" " + " ".join(keep)) if keep else ""

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in DROP:
            if tag not in DROP_VOID:
                self._skip += 1
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = True
        elif tag == "style":
            self._in_style = True
        elif tag in CHROME:
            self._chrome += 1
        self.out.append(f"<{tag}{self._attrs(attrs)}>")
        if tag in BLOCK:
            self.words.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag.lower() in DROP or self._skip:
            return
        self.out.append(f"<{tag.lower()}{self._attrs(attrs)} />")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in DROP:
            if tag not in DROP_VOID:
                self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "title":
            self._in_title = False
        elif tag == "style":
            self._in_style = False
        elif tag in CHROME:
            self._chrome = max(0, self._chrome - 1)
        if tag not in VOID:
            self.out.append(f"</{tag}>")
        if tag in BLOCK:
            self.words.append("\n")

    def handle_data(self, data):
        if self._skip:
            return
        if self._in_style:
            # CSS is emitted verbatim — escaping it would break selectors, and the parser
            # has already ended the element at </style, so nothing can close it early.
            self.out.append(data.replace("</", "<\\/"))
            return
        self.out.append(htmllib.escape(data, quote=False))
        if self._in_title:
            self.title += data
        elif data.strip() and not self._chrome:
            self.words.append(data)


def _clean_text(chunks: list[str]) -> str:
    text = "".join(chunks)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def _decode(body: bytes, content_type: str) -> str:
    m = re.search(r"charset=([\w-]+)", content_type)
    for enc in [m.group(1) if m else None, "utf-8", "cp1252"]:
        if not enc:
            continue
        try:
            return body.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return body.decode("utf-8", errors="replace")


def _render_html(raw: str, base_url: str) -> dict:
    parser = _Html()
    try:
        parser.feed(raw)
        parser.close()
    except Exception:
        pass
    body = "".join(parser.out)
    truncated = len(body) > MAX_HTML
    body = body[:MAX_HTML]
    text = _clean_text(parser.words)
    # Rendered inside sandbox="" — no scripts, no same-origin. The base tag resolves the
    # relative image links a filing uses; the reset only makes an unstyled document
    # readable, and a document bringing its own CSS overrides it.
    doc = (f'<!doctype html><html><head><meta charset="utf-8">'
           f'<base href="{htmllib.escape(base_url, quote=True)}">'
           f'<style>html{{background:#fff}}body{{background:#fff;color:#111;margin:0;padding:16px;'
           f'font:14px/1.55 -apple-system,Segoe UI,Roboto,sans-serif;overflow-wrap:anywhere}}'
           f'img{{max-width:100%;height:auto}}table{{border-collapse:collapse;max-width:100%}}'
           f'td,th{{padding:2px 6px}}</style></head><body>{body}</body></html>')
    return {"render": "html", "html": doc, "text": text[:MAX_TEXT],
            "text_truncated": len(text) > MAX_TEXT, "truncated": truncated,
            "title": parser.title.strip() or None}


async def document(props: dict) -> dict:
    """Fetch the artifact's source document and say how it should be shown."""
    url = (props.get("url") or "").strip()
    if not url:
        return {"status": "unavailable", "note": "This artifact has no source URL."}
    try:
        host = (httpx.URL(url).host or "").lower()
    except Exception:
        return {"status": "unavailable", "url": url, "note": "The artifact's URL could not be parsed."}
    # With no document to show, the UI's remaining option is to frame the live page — so
    # say whether that will work rather than leaving it to render an empty frame.
    for suffix, note in NO_DOCUMENT.items():
        if host == suffix or host.endswith("." + suffix):
            return {"status": "unavailable", "url": url, "note": note, "frameable": await frameable(url)}
    try:
        doc = await fetch_document(url)
    except HttpError as e:
        return {"status": "error", "url": url, "note": f"The source would not serve the document: {e}",
                "frameable": await frameable(url)}
    except Exception as e:  # network down, DNS, TLS
        return {"status": "error", "url": url, "note": f"Could not fetch the source document: {e}",
                "frameable": await frameable(url)}

    ctype = doc["content_type"]
    mime = ctype.split(";")[0].strip()
    size = len(doc["body"])
    stamp = doc.get("retrieved_at")
    meta = {"status": "ok", "url": doc["url"], "content_type": mime, "bytes": size, "capped": doc.get("truncated", False),
            "retrieved_at": datetime.fromtimestamp(stamp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if stamp else None}
    if mime in ("text/html", "application/xhtml+xml"):
        return {**meta, **_render_html(_decode(doc["body"], ctype), doc["url"])}
    if mime == "application/pdf":
        return {**meta, "render": "pdf"}
    if mime.startswith("image/"):
        return {**meta, "render": "image"}
    if mime in ("application/json", "application/ld+json"):
        text = _decode(doc["body"], ctype)
        try:
            text = json.dumps(json.loads(text), indent=2)
        except Exception:
            pass
        return {**meta, "render": "text", "text": text[:MAX_TEXT], "text_truncated": len(text) > MAX_TEXT}
    if mime.startswith("text/") or mime.endswith(("+xml", "/xml")):
        text = _decode(doc["body"], ctype)
        return {**meta, "render": "text", "text": text[:MAX_TEXT], "text_truncated": len(text) > MAX_TEXT}
    return {**meta, "render": "binary", "note": f"{mime} — {size:,} bytes. Open the source link to download it."}
