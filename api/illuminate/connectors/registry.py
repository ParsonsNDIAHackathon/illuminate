from __future__ import annotations

from .base import Connector
from .edgar import EDGARConnector
from .gdelt import GDELTConnector
from .gleif import GLEIFConnector
from .littlesis import LittleSisConnector
from .market import MarketConnector
from .ofac import OFACConnector
from .opencorporates import OpenCorporatesConnector
from .sam import SAMConnector
from .sam_exclusions import SAMExclusionsConnector
from .un_sanctions import UNSanctionsConnector
from .usaspending import USAspendingConnector
from .websearch import WebSearchConnector


class OpenAIPseudoConnector(Connector):
    """Not a data source — listed so the settings screen shows the model key."""
    name = "openai"
    label = "OpenAI"
    description = "Chat, extraction, Cypher generation (user-supplied key)"
    trust = "open"
    key_name = "openai"
    key_url = "https://platform.openai.com/api-keys"
    key_note = "Your key; inference cost sits with your account. Without it the app degrades to graph browsing and templates."

    async def enrich(self, entity, user):
        return []


REGISTRY: list[Connector] = [
    SAMConnector(), SAMExclusionsConnector(), USAspendingConnector(), GLEIFConnector(), LittleSisConnector(), EDGARConnector(), GDELTConnector(),
    OFACConnector(), UNSanctionsConnector(), MarketConnector(), OpenCorporatesConnector(), WebSearchConnector(), OpenAIPseudoConnector(),
]
_BY_NAME = {c.name: c for c in REGISTRY}


def get_connector(name: str) -> Connector | None:
    return _BY_NAME.get(name)


def connector_names() -> list[str]:
    return [c.name for c in REGISTRY]
