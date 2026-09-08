"""Reference tables the risk scorer reads: what a jurisdiction means, and what
sitting in one exposes you to.

Everything here is a *committed snapshot* of public reference material, in the same
spirit as the seed fixtures: the graph has to score offline, and a score that silently
depended on a live third-party index would be unreproducible. Each table names its
source and the date it was taken; `AS_OF` is what the report cites.

The tables are deliberately incomplete. A country that is not listed returns None and
the dimension records *no data* for it — never a zero. Imputing "not listed, therefore
safe" is the failure mode this whole module exists to avoid, so absence never scores.
"""
from __future__ import annotations

AS_OF = "2026-01"

# --- Jurisdiction classes -------------------------------------------------------
# home      the customer's own jurisdiction (this deployment is US DoD-facing)
# ally      treaty allies and major non-NATO allies — routine, disclosable
# partner   friendly non-allied states — ordinary commercial exposure
# neutral   no particular alignment; scored only in combination with other signals
# embargoed comprehensive US sanctions, arms embargo or state-sponsor designation
# covered   a "covered nation" under 10 U.S.C. § 4872(d) — China, Russia, North
#           Korea, Iran. This is the statutory term the NDAA sourcing rules use, and
#           it is the only class that scores high on its own.
HOME = "US"

COVERED_NATIONS = ("CN", "RU", "KP", "IR")

JURISDICTION_CLASS: dict[str, str] = {
    "US": "home",
    # NATO
    "AL": "ally", "BE": "ally", "BG": "ally", "CA": "ally", "HR": "ally", "CZ": "ally", "DK": "ally",
    "EE": "ally", "FI": "ally", "FR": "ally", "DE": "ally", "GR": "ally", "HU": "ally", "IS": "ally",
    "IT": "ally", "LV": "ally", "LT": "ally", "LU": "ally", "ME": "ally", "NL": "ally", "MK": "ally",
    "NO": "ally", "PL": "ally", "PT": "ally", "RO": "ally", "SK": "ally", "SI": "ally", "ES": "ally",
    "SE": "ally", "TR": "ally", "GB": "ally", "UK": "ally",
    # Major non-NATO allies and AUKUS/Five Eyes partners
    "AU": "ally", "NZ": "ally", "JP": "ally", "KR": "ally", "IL": "ally", "SG": "partner",
    "AR": "partner", "BH": "ally", "BR": "partner", "CO": "ally", "EG": "ally", "JO": "ally",
    "KW": "ally", "MA": "ally", "PH": "ally", "QA": "ally", "TH": "ally", "TN": "ally", "TW": "partner",
    # Frequent commercial counterparties, no alliance
    "IN": "partner", "MX": "partner", "CH": "partner", "AT": "partner", "IE": "partner", "MY": "partner",
    "ID": "neutral", "VN": "neutral", "ZA": "neutral", "AE": "partner", "SA": "partner", "CL": "partner",
    "CR": "partner", "UY": "partner", "PE": "neutral", "KZ": "neutral", "UZ": "neutral", "RS": "neutral",
    "UA": "partner", "GE": "partner", "MD": "neutral", "AM": "neutral", "AZ": "neutral",
    # Offshore jurisdictions: not adversarial, but opaque — see OPAQUE_JURISDICTIONS
    "HK": "neutral", "MO": "neutral", "KY": "neutral", "VG": "neutral", "BM": "neutral", "PA": "neutral",
    "SC": "neutral", "MU": "neutral", "LI": "neutral", "MT": "neutral", "CY": "neutral", "JE": "neutral",
    "GG": "neutral", "IM": "neutral", "BS": "neutral", "BZ": "neutral", "MH": "neutral",
    # Comprehensive sanctions / arms embargo / state sponsor of terrorism
    "CU": "embargoed", "SY": "embargoed", "VE": "embargoed", "BY": "embargoed", "MM": "embargoed",
    "AF": "embargoed", "SD": "embargoed", "ZW": "embargoed", "NI": "embargoed",
    # Covered nations (10 U.S.C. § 4872(d))
    "CN": "covered", "RU": "covered", "KP": "covered", "IR": "covered",
}

# Jurisdictions whose corporate registries do not disclose beneficial ownership, so a
# chain that passes through one cannot be walked to its end. Opacity is not adversity;
# it scores a step below a covered nation and says so.
OPAQUE_JURISDICTIONS = frozenset({"HK", "MO", "KY", "VG", "BM", "PA", "SC", "MU", "LI", "JE", "GG", "IM", "BS", "BZ", "MH", "AE"})

# What each class contributes when it turns up as a jurisdiction of incorporation,
# ultimate-parent seat, operation or manufacture. Severities are the report's own
# vocabulary (report.SEVERITY_WEIGHT), so an indicator reads the same wherever it lands.
CLASS_SEVERITY: dict[str, str] = {
    "home": "clear", "ally": "clear", "partner": "low", "neutral": "low",
    "embargoed": "high", "covered": "high",
}

CLASS_LABEL: dict[str, str] = {
    "home": "domestic",
    "ally": "allied jurisdiction",
    "partner": "partner jurisdiction",
    "neutral": "non-aligned jurisdiction",
    "embargoed": "sanctioned or arms-embargoed jurisdiction",
    "covered": "covered nation (10 U.S.C. § 4872)",
}


# --- Regional conflict ----------------------------------------------------------
# Countries with an active armed conflict or sustained large-scale political violence.
# Snapshot of the widely-reported conflict picture at AS_OF; the intent is "is a
# facility here exposed to organised violence", not a casualty count. Refresh by hand,
# or replace with a live feed — see refresh_note().
#   high   — active interstate or major internal armed conflict on national territory
#   medium — insurgency, sustained terrorism or criminal violence at scale, regionalised
CONFLICT: dict[str, str] = {
    "UA": "high", "RU": "high", "SY": "high", "YE": "high", "SD": "high", "SS": "high",
    "MM": "high", "SO": "high", "ML": "high", "BF": "high", "NE": "high", "CD": "high",
    "PS": "high", "IL": "medium", "LB": "medium", "HT": "high", "AF": "high", "LY": "high",
    "CF": "high", "ET": "medium", "NG": "medium", "IQ": "medium", "CM": "medium",
    "MZ": "medium", "TD": "medium", "CO": "medium", "MX": "medium", "PK": "medium",
    "IR": "medium", "AM": "medium", "AZ": "medium", "KP": "medium", "TW": "medium",
    "BD": "medium", "EC": "medium", "VE": "medium",
}

# --- Natural hazard -------------------------------------------------------------
# Exposure to natural hazards — earthquake, tropical cyclone, flood, volcano, tsunami,
# drought. Banded from the INFORM Risk index's hazard-and-exposure dimension
# (drmkc.jrc.ec.europa.eu/inform-index); bands, not the raw score, because the band is
# the only part stable enough to commit.
HAZARD: dict[str, str] = {
    "PH": "high", "ID": "high", "IN": "high", "BD": "high", "MM": "high", "JP": "high",
    "CN": "high", "PK": "high", "VN": "high", "NP": "high", "HT": "high", "MX": "high",
    "PG": "high", "TW": "high", "CL": "high", "PE": "high", "EC": "high", "GT": "high",
    "HN": "high", "NI": "high", "MZ": "high", "MG": "high", "SO": "high", "AF": "high",
    "IR": "high", "TR": "high", "LK": "medium", "TH": "medium", "MY": "medium", "KH": "medium",
    "US": "medium", "IT": "medium", "GR": "medium", "CO": "medium", "CR": "medium",
    "DO": "medium", "NZ": "medium", "AU": "medium", "DZ": "medium", "MA": "medium",
    "RO": "medium", "PT": "medium", "ES": "medium", "KR": "medium", "ZA": "medium",
    "BR": "medium", "AR": "medium", "EG": "medium", "KZ": "medium", "UZ": "medium",
    "GB": "low", "UK": "low", "IE": "low", "FR": "low", "DE": "low", "NL": "low", "BE": "low",
    "LU": "low", "AT": "low", "CH": "low", "SE": "low", "NO": "low", "DK": "low", "FI": "low",
    "PL": "low", "CZ": "low", "SK": "low", "HU": "low", "SI": "low", "EE": "low", "LV": "low",
    "LT": "low", "CA": "low", "SG": "low", "IL": "low", "AE": "low", "QA": "low", "KW": "low",
    "BH": "low", "SA": "low", "JO": "low", "UY": "low",
}

# US states and territories, banded from the FEMA National Risk Index expected-annual-loss
# rating (hazards.fema.gov/nri). EDGAR gives a state of incorporation and USAspending a
# place of performance, so a "US-XX" code is the commonest location in the graph after "US".
US_STATE_HAZARD: dict[str, str] = {
    "CA": "high", "TX": "high", "FL": "high", "LA": "high", "OK": "high", "MS": "high",
    "AL": "high", "PR": "high", "MO": "high", "AR": "high", "NC": "high", "NY": "high",
    "WA": "medium", "OR": "medium", "SC": "medium", "GA": "medium", "VA": "medium",
    "TN": "medium", "KY": "medium", "KS": "medium", "NE": "medium", "IA": "medium",
    "IL": "medium", "NJ": "medium", "AK": "medium", "HI": "medium", "AZ": "medium",
    "NM": "medium", "CO": "medium", "NV": "medium", "MN": "medium", "IN": "medium",
    "OH": "medium", "PA": "medium", "MA": "medium",
    "UT": "low", "ID": "low", "MT": "low", "WY": "low", "ND": "low", "SD": "low",
    "WI": "low", "MI": "low", "WV": "low", "MD": "low", "DE": "low", "DC": "low",
    "CT": "low", "RI": "low", "NH": "low", "VT": "low", "ME": "low",
}

HAZARD_SOURCE = "INFORM Risk (hazard & exposure) · FEMA National Risk Index"
CONFLICT_SOURCE = "curated conflict snapshot"
JURISDICTION_SOURCE = "10 U.S.C. § 4872 covered nations · NATO/MNNA rosters · OFAC country programs"


def _split(code: str | None) -> tuple[str | None, str | None]:
    """'US-TX' -> ('US', 'TX'); 'CN' -> ('CN', None). Anything else -> (None, None)."""
    c = (code or "").strip().upper()
    if not c:
        return None, None
    if "-" in c:
        country, _, region = c.partition("-")
        return (country or None), (region or None)
    return c, None


def jurisdiction_class(code: str | None) -> str | None:
    """The class of a location code, or None when the code is not one we classify."""
    country, _ = _split(code)
    return JURISDICTION_CLASS.get(country) if country else None


def is_foreign(code: str | None) -> bool | None:
    country, _ = _split(code)
    if not country:
        return None
    return country != HOME


def is_opaque(code: str | None) -> bool:
    country, _ = _split(code)
    return bool(country) and country in OPAQUE_JURISDICTIONS


def conflict_level(code: str | None) -> str | None:
    country, _ = _split(code)
    return CONFLICT.get(country) if country else None


def hazard_level(code: str | None) -> str | None:
    """Natural-hazard band. A US state code resolves against the state table; every
    other region falls back to its country."""
    country, region = _split(code)
    if not country:
        return None
    if country == HOME and region:
        return US_STATE_HAZARD.get(region, HAZARD.get(HOME))
    return HAZARD.get(country)


def known(code: str | None) -> bool:
    """Whether any table has something to say about this code. A location we know
    nothing about must not be scored as safe."""
    country, region = _split(code)
    if not country:
        return False
    return bool(
        country in JURISDICTION_CLASS or country in CONFLICT or country in HAZARD
        or (country == HOME and region in US_STATE_HAZARD)
    )


def refresh_note() -> str:
    return (
        f"Jurisdiction, conflict and hazard tables are a committed snapshot as of {AS_OF} "
        f"({JURISDICTION_SOURCE}; {CONFLICT_SOURCE}; {HAZARD_SOURCE}). Countries absent from a "
        "table score as no-data, not as clear."
    )
