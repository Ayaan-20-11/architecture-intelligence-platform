import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class SourcesConfig(BaseModel):
    directories: list[Path] = Field(default_factory=lambda: [Path("./repositories")])


class GraphConfig(BaseModel):
    uri: str = "bolt://localhost:7687"
    database: str = "neo4j"
    max_traversal_depth: int = 5


class ImportConfig(BaseModel):
    openapi: bool = True
    asyncapi: bool = True
    architecture_manifest: bool = True


class LLMConfig(BaseModel):
    enabled: bool = True
    max_result_rows: int = 100


class AppConfig(BaseModel):
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    graph: GraphConfig = Field(default_factory=GraphConfig)
    import_: ImportConfig = Field(default_factory=ImportConfig, alias="import")
    llm: LLMConfig = Field(default_factory=LLMConfig)

    model_config = {"populate_by_name": True}


class Secrets(BaseModel):
    neo4j_user: str
    neo4j_password: str
    anthropic_api_key: str | None = None


@dataclass(frozen=True)
class Settings:
    config: AppConfig
    secrets: Secrets


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"required environment variable {name} is not set")
    return value


def load_config(path: Path) -> AppConfig:
    """Loads the spec §17.1 YAML shape; NEO4J_URI env var overrides graph.uri (matches docker-compose.yml)."""
    raw = yaml.safe_load(path.read_text()) or {}
    config = AppConfig.model_validate(raw.get("architecture_intelligence", {}))
    uri_override = os.environ.get("NEO4J_URI")
    if uri_override:
        config = config.model_copy(
            update={"graph": config.graph.model_copy(update={"uri": uri_override})}
        )
    return config


def load_secrets() -> Secrets:
    """Reads NEO4J_USER/NEO4J_PASSWORD/ANTHROPIC_API_KEY from the environment (spec §17.2) - never from the repo."""
    return Secrets(
        neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
        neo4j_password=_require_env("NEO4J_PASSWORD"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
    )


def load_settings(config_path: Path) -> Settings:
    return Settings(config=load_config(config_path), secrets=load_secrets())
