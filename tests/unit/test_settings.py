from pathlib import Path

import pytest

from app.settings import load_config, load_secrets, load_settings

CONFIG_YAML = """
architecture_intelligence:
  sources:
    directories:
      - examples
  graph:
    uri: bolt://localhost:7687
    database: neo4j
    max_traversal_depth: 5
  import:
    openapi: true
    asyncapi: false
    architecture_manifest: true
  llm:
    enabled: true
    max_result_rows: 100
"""


def test_load_config_parses_spec_shape(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)

    config = load_config(config_path)

    assert config.sources.directories == [Path("examples")]
    assert config.graph.uri == "bolt://localhost:7687"
    assert config.graph.database == "neo4j"
    assert config.graph.max_traversal_depth == 5
    assert config.import_.openapi is True
    assert config.import_.asyncapi is False
    assert config.llm.max_result_rows == 100


def test_load_config_defaults_on_empty_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("architecture_intelligence: {}\n")

    config = load_config(config_path)

    assert config.graph.database == "neo4j"
    assert config.import_.openapi is True


def test_neo4j_uri_env_var_overrides_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")

    config = load_config(config_path)

    assert config.graph.uri == "bolt://neo4j:7687"


def test_load_secrets_reads_environment(monkeypatch):
    monkeypatch.setenv("NEO4J_USER", "custom-user")
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    secrets = load_secrets()

    assert secrets.neo4j_user == "custom-user"
    assert secrets.neo4j_password == "secret"
    assert secrets.openai_api_key == "sk-test"


def test_load_secrets_defaults_neo4j_user(monkeypatch):
    monkeypatch.delenv("NEO4J_USER", raising=False)
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    secrets = load_secrets()

    assert secrets.neo4j_user == "neo4j"
    assert secrets.openai_api_key is None


def test_load_secrets_raises_without_password(monkeypatch):
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    with pytest.raises(RuntimeError, match="NEO4J_PASSWORD"):
        load_secrets()


def test_load_settings_combines_config_and_secrets(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(CONFIG_YAML)
    monkeypatch.setenv("NEO4J_PASSWORD", "secret")

    settings = load_settings(config_path)

    assert settings.config.graph.database == "neo4j"
    assert settings.secrets.neo4j_password == "secret"
