import asyncio
import json

import pytest

from illuminate.connectors.base import ArtifactRef, Fact, NodeRef
from illuminate.connectors.registry import REGISTRY
from illuminate.connectors.validation import (
    check_live_source,
    validate_facts,
    validation_matrix,
)


def test_validation_matrix_covers_registry_with_bounded_non_cached_probes():
    rows = validation_matrix()
    assert [row.name for row in rows] == [connector.name for connector in REGISTRY]
    assert len({row.name for row in rows}) == len(rows)
    for row, connector in zip(rows, REGISTRY, strict=True):
        assert row.credential_required is connector.needs_key()
        assert row.entity_kinds == connector.kinds
        assert 0 < row.diagnostic_max_bytes <= 65536
        assert row.source_id
        assert row.retrieval_mode == "non_cached_read_only_probe"
        assert callable(connector.check_connectivity)


@pytest.mark.parametrize("connector", REGISTRY, ids=lambda connector: connector.name)
def test_every_source_has_complete_registry_and_provenance_contract(connector):
    data = connector.to_dict()
    assert data["name"] == connector.name
    assert data["trust"] in {"authoritative", "open"}
    assert data["kinds"]
    assert data["source_id"]
    assert data["endpoint"] is None or data["endpoint"].startswith("https://")
    if connector.name not in {"openai", "websearch"}:
        assert connector.diagnostic_url.startswith("https://")
        assert "$credential" not in connector.diagnostic_url


@pytest.mark.parametrize("connector", REGISTRY, ids=lambda connector: connector.name)
def test_normalized_production_fact_contract_for_every_source(connector):
    fact = Fact(
        subject=NodeRef("Entity", "ent_validation"),
        predicate="attr:source_check",
        value=connector.name,
        confidence=0.8,
        artifact=ArtifactRef(
            url=f"https://evidence.invalid/{connector.name}",
            title=f"{connector.label} record",
            source=connector.name,
            props={"source_identifier": f"{connector.name}:stable-record"},
        ),
    )
    validate_facts(connector.name, [fact])


@pytest.mark.parametrize(
    "fact",
    [
        Fact(NodeRef("Entity", "e"), "attr:x", value="x", confidence=1.1),
        Fact(NodeRef("Entity", "e"), "attr:x", value="x", props={"simulated": True}),
        Fact(
            NodeRef("Entity", "e"),
            "attr:x",
            value="x",
            artifact=ArtifactRef("https://evidence.invalid/x", "Demo", source="test",
                                 props={"simulated": True}),
        ),
        Fact(
            NodeRef("Entity", "e"),
            "attr:x",
            value="x",
            artifact=ArtifactRef("javascript:alert(1)", "Record", source="test"),
        ),
        Fact(NodeRef("Entity", "e", {"simulated": True}), "attr:x", value="x"),
        Fact(
            NodeRef("Entity", "e"),
            "LINKS",
            object=NodeRef("Entity", "o", {"simulated": True}),
        ),
    ],
)
def test_production_fact_validation_rejects_unsafe_or_simulated_output(fact):
    with pytest.raises(ValueError):
        validate_facts("source", [fact])


def test_production_fact_validation_preserves_upstream_http_citations():
    fact = Fact(
        NodeRef("Entity", "e"),
        "mention",
        artifact=ArtifactRef("http://publisher.example/article", "Article", source="GDELT"),
    )
    validate_facts("gdelt", [fact])


def test_smoke_classification_is_allowlisted_and_redacted():
    secret = "never-return-provider-secret"

    class Connector:
        name = "example"
        diagnostic_auth_statuses = (401, 403)
        def needs_key(self):
            return True
        async def status(self, user):
            return {"connected": True}
        async def check_connectivity(self, user):
            raise RuntimeError(secret)

    result = asyncio.run(check_live_source(Connector()))
    assert result == {
        "source": "example",
        "status": "contract_failed",
        "reason": "provider response did not match its contract",
    }
    assert secret not in json.dumps(result)


def test_smoke_skips_unconfigured_credentials_without_a_probe():
    called = False

    class Connector:
        name = "credentialed"
        diagnostic_auth_statuses = (401, 403)
        def needs_key(self):
            return True
        async def status(self, user):
            return {"connected": False}
        async def check_connectivity(self, user):
            nonlocal called
            called = True

    assert asyncio.run(check_live_source(Connector()))["status"] == "skipped"
    assert called is False


def test_smoke_distinguishes_passed_auth_unavailable_and_contract_failure():
    class Connector:
        name = "example"
        diagnostic_auth_statuses = (401, 403)
        def needs_key(self):
            return False
        async def status(self, user):
            return {"connected": True}
        async def check_connectivity(self, user):
            return self.result

    connector = Connector()
    expected = [
        ({"ok": True, "status": "available"}, "passed"),
        ({"ok": False, "status": "authentication"}, "authentication_failed"),
        ({"ok": False, "status": "rate_limited"}, "unavailable"),
        ({"unexpected": True}, "contract_failed"),
        ({"ok": False, "status": []}, "contract_failed"),
    ]
    for connector.result, status in expected:
        assert asyncio.run(check_live_source(connector))["status"] == status


def test_smoke_bounds_and_redacts_status_failures():
    class Connector:
        name = "example"
        diagnostic_auth_statuses = (401, 403)

        def needs_key(self):
            return False

        async def status(self, user):
            raise OSError("raw provider response")

    result = asyncio.run(check_live_source(Connector()))
    assert result == {
        "source": "example",
        "status": "unavailable",
        "reason": "diagnostic request failed",
    }