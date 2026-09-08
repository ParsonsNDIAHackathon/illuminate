"""Opt-in, read-only checks of configured upstream connector diagnostics."""
import os

import pytest

from illuminate.connectors.registry import REGISTRY
from illuminate.connectors.validation import check_live_source

pytestmark = pytest.mark.live_sources


@pytest.mark.parametrize("connector", REGISTRY, ids=lambda connector: connector.name)
async def test_configured_live_source(connector, record_property):
    if os.getenv("ILLUMINATE_LIVE_SOURCE_TESTS") != "1":
        pytest.skip("set ILLUMINATE_LIVE_SOURCE_TESTS=1 to exercise live sources")
    result = await check_live_source(connector)
    record_property("live_source", result)
    if result["status"] == "skipped":
        pytest.skip(f"{connector.name}: {result['reason']}")
    assert result["status"] == "passed", (
        f"{connector.name}: {result['status']} ({result['reason']})"
    )