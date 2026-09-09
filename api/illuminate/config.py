from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

PermissionMode = Literal["ask_always", "auto_create", "session_allowlist"]


class Settings(BaseSettings):
    """Process-level settings. Everything here comes from the environment; per-user
    things (API keys, model choice, permission mode) live in the data dir."""

    # Two dotenv paths, relative to the working directory. The host dev loop runs from
    # api/, so "../.env" is the repo-root file compose also reads — one place to set
    # NEO4J_PASSWORD for both. An optional api/.env overrides it, and real environment
    # variables (what compose passes the container) override both.
    model_config = SettingsConfigDict(env_prefix="", env_file=("../.env", ".env"), extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "illuminate-dev"
    neo4j_database: str = "neo4j"

    illuminate_data_dir: Path = Path("./data")
    illuminate_cors_origins: str = "http://localhost:5173,http://localhost:8080"
    illuminate_user_agent: str = "Illuminate/0.1 (berge472@gmail.com)"

    # Query guard rails (D3)
    cypher_default_limit: int = 500
    cypher_max_limit: int = 2000
    cypher_max_hops: int = 6
    cypher_read_timeout_s: float = 20.0
    permission_timeout_s: float = 600.0

    # Default model tiers (D8). Overridable per user in workspace settings.
    model_strong: str = "gpt-5"
    model_fast: str = "gpt-5-mini"
    openai_base_url: str | None = None

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.illuminate_cors_origins.split(",") if o.strip()]

    @property
    def data_dir(self) -> Path:
        self.illuminate_data_dir.mkdir(parents=True, exist_ok=True)
        return self.illuminate_data_dir


settings = Settings()


# Canvas layers and whether each is drawn by default. "entities" is always on. Artifacts split by
# kind over "artifacts" (documents: filings, news, awards, web) and "sources" (registry entries and
# source records); "claims" is the reified assertions those artifacts evidence. "indirect_orgs" is
# a canvas-side filter, not a fetch layer: off, an organization is left undrawn unless a chain of
# contracts or ownership joins it to a program — people, places, documents, claims and affiliation
# edges (lobbying, memberships, donations) do not carry that chain, and ownership carries it only
# pointing in, so the owner of a supplier is drawn and that owner's other subsidiaries are not. A
# node scored over 20 that reaches a supplier is drawn either way (web/src/stores/graphLayers.ts).
# "reports" is on by default: a report exists because someone asked for it, and there are a handful
# of them at most, so hiding the thing the user just generated would be the surprising default.
LAYER_DEFAULTS = {"entities": True, "indirect_orgs": True, "people": True, "countries": False, "categories": False, "artifacts": False, "sources": False, "claims": False,
                  "reports": True}

# Risk score above which a node is drawn whatever the filters say, mirrored by RISK_PIN_FLOOR in
# web/src/stores/graphLayers.ts. The canvas can only pin what it was sent, so the graph queries
# carry risky people past an off "people" layer: hiding people is how the canvas gets readable and
# must not be how a designated director disappears. Just under the "elevated" band floor (risk.py).
RISK_PIN_FLOOR = 20


class WorkspaceSettings(BaseModel):
    """Single-workspace settings (multi-tenant auth is an explicit hackathon cut).

    No consumer lives here. A workspace holds every program at once; which one is in
    view is a property of the canvas the user is looking at, not of the workspace.
    """

    permission_mode: PermissionMode = "ask_always"
    model_strong: str | None = None
    model_fast: str | None = None
    openai_base_url: str | None = None
    layers: dict[str, bool] = dict(LAYER_DEFAULTS)


def _ws_path() -> Path:
    return settings.data_dir / "workspace.json"


def load_workspace() -> WorkspaceSettings:
    p = _ws_path()
    if p.exists():
        try:
            ws = WorkspaceSettings.model_validate_json(p.read_text())
            # A workspace saved before a layer existed keeps its choices and gains the new default.
            ws.layers = {**LAYER_DEFAULTS, **ws.layers}
            return ws
        except Exception:
            pass
    return WorkspaceSettings()


def save_workspace(ws: WorkspaceSettings) -> WorkspaceSettings:
    _ws_path().write_text(json.dumps(ws.model_dump(), indent=2))
    return ws
