"""Read-only validation contracts for registered external capabilities.

Deterministic tests consume ``validation_matrix``.  The live runner uses only
the connector diagnostic methods: it never calls ``enrich`` and therefore
cannot stage claims or mutate the graph.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

import httpx

from .base import Fact
from .http import HttpError
from .registry import REGISTRY

SmokeStatus = Literal[
    "passed", "skipped", "authentication_failed", "unavailable", "contract_failed"
]


@dataclass(frozen=True)
class SourceValidation:
    name: str
    credential_required: bool
    entity_kinds: tuple[str, ...]
    diagnostic_max_bytes: int
    source_id: str
    retrieval_mode: Literal["non_cached_read_only_probe"] = "non_cached_read_only_probe"

_EXPECTED_SOURCES = {
    "sam": (True, ("organization",), 65536, "sam-entity-management"),
    "sam_exclusions": (False, ("organization",), 4096, "sam-exclusions-public-extract"),
    "usaspending": (False, ("organization", "program", "agency"), 4096, "usaspending.gov"),
    "gleif": (False, ("organization",), 4096, "gleif-lei"),
    "littlesis": (False, ("organization",), 4096, "littlesis"),
    "edgar": (False, ("organization",), 4096, "sec-edgar"),
    "gdelt": (False, ("organization", "program", "agency"), 4096, "gdelt-2.x"),
    "ofac": (False, ("organization",), 4096, "ofac-sdn"),
    "un_sanctions": (False, ("organization",), 4096, "un-sc-consolidated"),
    "market": (True, ("organization",), 4096, "finnhub"),
    "opencorporates": (True, ("organization",), 4096, "opencorporates"),
    "openstreetmap": (False, ("organization", "program", "agency", "facility", "route"), 4096, "openstreetmap"),
    "far": (False, ("organization", "program", "agency"), 4096, "ecfr-title-48"),
    "epss": (False, ("organization", "program", "agency"), 4096, "first-epss"),
    "websearch": (True, ("organization",), 65536, "websearch"),
    "openai": (True, ("organization",), 65536, "openai"),
}


def validation_matrix() -> tuple[SourceValidation, ...]:
    """Return source-specific expectations independent of registry construction."""
    return tuple(
        SourceValidation(
            name=name,
            credential_required=expected[0],
            entity_kinds=expected[1],
            diagnostic_max_bytes=expected[2],
            source_id=expected[3],
        )
        for name, expected in _EXPECTED_SOURCES.items()
    )


def validate_facts(source: str, facts: list[Fact]) -> None:
    """Reject connector output that is unsafe to stage as production evidence."""
    for fact in facts:
        if not isinstance(fact, Fact):
            raise ValueError(f"{source}: connector output is not a Fact")
        if not fact.subject.id or not fact.subject.label or not fact.predicate:
            raise ValueError(f"{source}: fact identity is incomplete")
        if fact.object is None and fact.value is None and fact.artifact is None:
            raise ValueError(f"{source}: fact has neither object nor value")
        if isinstance(fact.confidence, bool) or not 0 <= fact.confidence <= 1:
            raise ValueError(f"{source}: confidence is outside [0, 1]")
        if fact.props.get("simulated") or fact.subject.props.get("simulated") or (
            fact.object is not None and fact.object.props.get("simulated")
        ) or (
            fact.artifact is not None and fact.artifact.props.get("simulated")
        ):
            raise ValueError(f"{source}: live connector output is simulated")
        if fact.artifact is not None:
            try:
                artifact_url = httpx.URL(fact.artifact.url)
            except (TypeError, ValueError):
                raise ValueError(f"{source}: artifact URL is invalid") from None
            # Provider requests have their own HTTPS/public-network policies.
            # Evidence citations may legitimately preserve an upstream HTTP URL.
            if artifact_url.scheme not in ("http", "https") or not artifact_url.host:
                raise ValueError(f"{source}: artifact URL is not HTTP(S)")
            if not fact.artifact.source or not fact.artifact.title:
                raise ValueError(f"{source}: artifact provenance is incomplete")


def _safe_result(name: str, status: SmokeStatus, reason: str) -> dict:
    return {"source": name, "status": status, "reason": reason}


async def check_live_source(connector, user: str = "local") -> dict:
    """Run one bounded connectivity probe and normalize its public outcome."""
    async def operation():
        status = await connector.status(user)
        if connector.needs_key() and not status.get("connected"):
            return None
        return await connector.check_connectivity(user)

    try:
        result = await asyncio.wait_for(operation(), timeout=10)
    except (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException):
        return _safe_result(connector.name, "unavailable", "diagnostic timed out")
    except Exception as error:
        code = error.status if isinstance(error, HttpError) else getattr(error, "status_code", None)
        if code in connector.diagnostic_auth_statuses:
            return _safe_result(connector.name, "authentication_failed", "credential was rejected")
        if isinstance(error, RuntimeError):
            return _safe_result(connector.name, "contract_failed", "provider response did not match its contract")
        return _safe_result(connector.name, "unavailable", "diagnostic request failed")

    if result is None:
        return _safe_result(connector.name, "skipped", "credential is not configured")
    if not isinstance(result, dict) or result.get("ok") is not True or result.get("status") != "available":
        category = result.get("status") if isinstance(result, dict) else None
        if category == "missing_credentials":
            return _safe_result(connector.name, "skipped", "credential is not configured")
        if category == "authentication":
            return _safe_result(connector.name, "authentication_failed", "credential was rejected")
        if category in ("rate_limited", "timeout", "unavailable"):
            return _safe_result(connector.name, "unavailable", f"source reported {category}")
        return _safe_result(connector.name, "contract_failed", "unexpected diagnostic result")
    return _safe_result(connector.name, "passed", "bounded read-only diagnostic succeeded")


async def run_live_validation(user: str = "local") -> list[dict]:
    """Check every configured registry capability, preserving registry order."""
    return [await check_live_source(connector, user) for connector in REGISTRY]


def main() -> None:
    import json

    results = asyncio.run(run_live_validation())
    print(json.dumps(results, indent=2))
    if any(item["status"] in {"authentication_failed", "unavailable", "contract_failed"} for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()