from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import AppConfig, ConfigManager


DEFAULT_YAML = """
app:
  name: test-memory
  version: 1.0.0
storage:
  data_dir: ./test-data
  sqlite_file: test.db
embedding:
  provider: configurable
  model_name: test-model
vector_store:
  provider: memory
retrieval:
  top_k_default: 5
  candidate_k: 30
logging:
  level: INFO
"""


def write_config(config_dir: Path, name: str, content: str) -> None:
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / name).write_text(content, encoding="utf-8")


def test_loads_project_default_yaml(monkeypatch):
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)

    config = ConfigManager().load()

    assert isinstance(config, AppConfig)
    assert config.app.name == "os-agent-memory"
    assert config.embedding.provider == "mock"
    assert config.retrieval.top_k_default == 5


@pytest.mark.parametrize(
    ("environment", "embedding_provider", "vector_provider"),
    [
        ("development", "sentence_transformer", "faiss"),
        ("kylin", "kylin", "kylin"),
    ],
)
def test_loads_environment_yaml(
    monkeypatch, environment, embedding_provider, vector_provider
):
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)

    config = ConfigManager(environment=environment).load()

    assert config.embedding.provider == embedding_provider
    assert config.vector_store.provider == vector_provider
    assert config.embedding.model_name == "default"


def test_environment_variable_overrides_nested_values(tmp_path, monkeypatch):
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    write_config(tmp_path, "default.yaml", DEFAULT_YAML)
    monkeypatch.setenv("OS_AGENT_EMBEDDING__PROVIDER", "runtime_provider")
    monkeypatch.setenv("OS_AGENT_RETRIEVAL__TOP_K_DEFAULT", "17")

    config = ConfigManager(config_dir=tmp_path).load()

    assert config.embedding.provider == "runtime_provider"
    assert config.retrieval.top_k_default == 17


def test_config_directory_can_come_from_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)
    write_config(tmp_path, "default.yaml", DEFAULT_YAML)
    monkeypatch.setenv("OS_AGENT_CONFIG_DIR", str(tmp_path))

    manager = ConfigManager()

    assert manager.load().app.name == "test-memory"
    assert manager.config_dir == tmp_path.resolve()


def test_get_returns_full_config_and_dotted_values(tmp_path, monkeypatch):
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    write_config(tmp_path, "default.yaml", DEFAULT_YAML)
    manager = ConfigManager(config_dir=tmp_path)

    assert isinstance(manager.get(), AppConfig)
    assert manager.get("embedding.provider") == "configurable"
    assert manager.get("missing.value", "fallback") == "fallback"
    with pytest.raises(KeyError):
        manager.get("missing.value")


def test_reload_rereads_yaml_and_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    write_config(tmp_path, "default.yaml", DEFAULT_YAML)
    manager = ConfigManager(config_dir=tmp_path)
    first = manager.load()

    updated_yaml = DEFAULT_YAML.replace("level: INFO", "level: DEBUG")
    write_config(tmp_path, "default.yaml", updated_yaml)
    monkeypatch.setenv("OS_AGENT_EMBEDDING__MODEL_NAME", "runtime-model")
    reloaded = manager.reload()

    assert reloaded is not first
    assert reloaded.logging.level == "DEBUG"
    assert reloaded.embedding.model_name == "runtime-model"


def test_invalid_configuration_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    invalid_yaml = DEFAULT_YAML.replace("top_k_default: 5", "top_k_default: 0")
    write_config(tmp_path, "default.yaml", invalid_yaml)

    with pytest.raises(ValidationError):
        ConfigManager(config_dir=tmp_path).load()


def test_non_mapping_yaml_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    write_config(tmp_path, "default.yaml", "- item\n- item\n")

    with pytest.raises(ValueError, match="root must be a mapping"):
        ConfigManager(config_dir=tmp_path).load()


def test_missing_profile_is_rejected(tmp_path, monkeypatch):
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    write_config(tmp_path, "default.yaml", DEFAULT_YAML)

    with pytest.raises(FileNotFoundError):
        ConfigManager(config_dir=tmp_path, environment="missing").load()


def test_profile_name_cannot_escape_config_directory(tmp_path, monkeypatch):
    monkeypatch.delenv("OS_AGENT_ENV", raising=False)
    monkeypatch.delenv("OS_AGENT_CONFIG_DIR", raising=False)
    write_config(tmp_path, "default.yaml", DEFAULT_YAML)

    with pytest.raises(ValueError, match="invalid configuration environment"):
        ConfigManager(config_dir=tmp_path, environment="../outside").load()
