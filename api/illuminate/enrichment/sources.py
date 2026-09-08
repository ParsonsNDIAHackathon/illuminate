"""Context-aware connector selection, kept separate from registry construction.

The small interface is intentionally easy for coverage/capability policy modules
to call or extend without changing the global connector registry.
"""
from __future__ import annotations

from collections.abc import Iterable

from ..connectors.base import Connector

COMPLETED_SOURCE_STATES = {"succeeded", "empty"}


def select_connectors(
    entity: dict,
    connectors: Iterable[Connector],
    *,
    requested: list[str] | None = None,
    previous_results: dict | None = None,
) -> list[str]:
    """Return applicable sources in stable order.

    Explicit requests retain unknown/inapplicable names so the worker can report
    them truthfully. Automatic selection omits sources that cannot speak about
    the entity. On resume, successfully completed sources are not run again;
    partial and failed sources remain eligible.
    """
    available = list(connectors)
    if requested is None:
        names = [
            connector.name
            for connector in available
            if connector.name != "openai" and connector.applies_to(entity)
        ]
    else:
        names = list(dict.fromkeys(requested))
    if previous_results:
        names = [
            name for name in names
            if not (
                isinstance(previous_results.get(name), dict)
                and previous_results[name].get("status") in COMPLETED_SOURCE_STATES
            )
        ]
    return names