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

    model_config = SettingsConfigDict(env_prefix="", env_file=".env", extra="ignore")

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


class WorkspaceSettings(BaseModel):
    """Single-workspace settings (multi-tenant auth is an explicit hackathon cut)."""

    root_id: str | None = None
    root_label: str | None = None
    permission_mode: PermissionMode = "ask_always"
    model_strong: str | None = None
    model_fast: str | None = None
    openai_base_url: str | None = None
    layers: dict[str, bool] = {"entities": True, "people": True, "countries": False, "artifacts": False}


def _ws_path() -> Path:
    return settings.data_dir / "workspace.json"


def load_workspace() -> WorkspaceSettings:
    p = _ws_path()
    if p.exists():
        try:
            return WorkspaceSettings.model_validate_json(p.read_text())
        except Exception:
            pass
    return WorkspaceSettings()


def save_workspace(ws: WorkspaceSettings) -> WorkspaceSettings:
    _ws_path().write_text(json.dumps(ws.model_dump(), indent=2))
    return ws
