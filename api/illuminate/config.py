from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PermissionMode = Literal["ask_always", "auto_create", "session_allowlist"]


class Settings(BaseSettings):
    """Process-level settings. Everything here comes from the environment; per-user
    things (API keys, model choice, permission mode) live in the data dir."""

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    illuminate_data_dir: Path = Path("./data")
    illuminate_cors_origins: str = "http://localhost:5173,http://localhost:8080"
    illuminate_user_agent: str = "Illuminate/0.1 (operator contact not configured)"

    # Query guard rails (D3)
    cypher_default_limit: int = 500
    cypher_max_limit: int = 2000
    cypher_max_hops: int = 6
    cypher_read_timeout_s: float = 20.0
    cypher_write_timeout_s: float = 20.0
    permission_timeout_s: float = 600.0
    connector_timeout_s: float = 45.0
    connector_retries: int = 1
    connector_processing_timeout_s: float = 60.0
    enrichment_job_timeout_s: float = 180.0
    summary_timeout_s: float = 30.0
    readiness_timeout_s: float = 3.0
    readiness_cache_s: float = 10.0
    freshness_stale_hours: float = 168.0

    # Default model tiers (D8). Overridable per user in workspace settings.
    model_strong: str = "gpt-5"
    model_fast: str = "gpt-5-mini"
    openai_base_url: str | None = None
    session_secret: SecretStr = SecretStr(secrets.token_urlsafe(32))
    # Streamable HTTP MCP is disabled unless an operator supplies a dedicated
    # bearer token. Stdio MCP remains available for local, process-bound use.
    illuminate_mcp_http_token: SecretStr | None = None

    # NDIA catalog publishing. Credentials remain process-only and are never
    # included in API responses or workspace settings.
    ndia_key: SecretStr | None = None
    ndia_catalog_base_url: str = "https://hackathon.ndia.org"
    # Write endpoints are intentionally opt-in because the public portal only
    # documents its read contract. Set these to the organizer-provided paths.
    ndia_catalog_contribution_path: str | None = None
    ndia_catalog_lookup_path: str | None = None
    ndia_catalog_status_path: str | None = None
    ndia_catalog_api_key_header: str = "X-API-Key"
    ndia_catalog_timeout_s: float = 20.0
    ndia_catalog_operator_token: SecretStr | None = None
    illuminate_public_url: str | None = None

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
# source records); "claims" is the reified assertions those artifacts evidence.
LAYER_DEFAULTS = {"entities": True, "people": True, "countries": False, "categories": False, "artifacts": False, "sources": False, "claims": False}


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
