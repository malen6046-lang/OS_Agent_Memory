"""YAML configuration loading with Pydantic validation and env overrides."""

from __future__ import annotations

import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Annotated, Any, Literal, Mapping

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints


NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
DEFAULT_CONFIG_FILE = "default.yaml"
DEFAULT_CONFIG_DIRECTORY = "configs"
DEFAULT_ENV_PREFIX = "OS_AGENT_"
PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_MISSING = object()


class ApplicationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyString
    version: NonEmptyString


class StorageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: Path
    sqlite_file: NonEmptyString


class EmbeddingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: NonEmptyString
    model_name: NonEmptyString
    implementation: NonEmptyString | None = None


class VectorStoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: NonEmptyString
    implementation: NonEmptyString | None = None


class ServicesConfig(BaseModel):
    """Select mock services or explicitly configured real implementations."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["mock", "real"] = "mock"
    preference_implementation: NonEmptyString | None = None
    safety_implementation: NonEmptyString | None = None
    forget_implementation: NonEmptyString | None = None
    knowledge_implementation: NonEmptyString | None = None
    retriever_implementation: NonEmptyString | None = None


class RetrievalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    top_k_default: int = Field(gt=0)
    candidate_k: int = Field(gt=0)


class LoggingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: NonEmptyString


class AppConfig(BaseModel):
    """Validated application configuration."""

    model_config = ConfigDict(extra="forbid")

    app: ApplicationConfig
    storage: StorageConfig
    embedding: EmbeddingConfig
    vector_store: VectorStoreConfig
    retrieval: RetrievalConfig
    logging: LoggingConfig
    services: ServicesConfig = Field(default_factory=ServicesConfig)


class ConfigManager:
    """Load, query, and reload layered YAML application configuration."""

    def __init__(
        self,
        config_dir: str | Path | None = None,
        environment: str | None = None,
        env_prefix: str = DEFAULT_ENV_PREFIX,
    ) -> None:
        self._env_prefix = env_prefix.upper()
        self._config_dir = self._resolve_config_dir(config_dir)
        self._environment = environment
        self._config: AppConfig | None = None

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    def load(self, environment: str | None = None) -> AppConfig:
        """Load default YAML, apply a profile, then apply environment values."""
        if environment is not None:
            self._environment = environment

        profile = self._selected_environment()
        merged = self._read_yaml(self._config_dir / DEFAULT_CONFIG_FILE)

        if profile != "default":
            profile_file = self._profile_file(profile)
            merged = self._deep_merge(merged, self._read_yaml(profile_file))

        self._apply_environment_overrides(merged)
        self._config = AppConfig.model_validate(merged)
        return self._config

    def get(self, key: str | None = None, default: Any = _MISSING) -> Any:
        """Return the full config or one dot-separated value."""
        config = self._config or self.load()
        if key is None:
            return config
        if not key or any(not part for part in key.split(".")):
            raise ValueError("configuration key must be a non-empty dotted path")

        current: Any = config
        for part in key.split("."):
            if isinstance(current, BaseModel) and part in type(current).model_fields:
                current = getattr(current, part)
            elif isinstance(current, Mapping) and part in current:
                current = current[part]
            elif default is not _MISSING:
                return default
            else:
                raise KeyError(key)
        return current

    def reload(self) -> AppConfig:
        """Discard the current object and reload files and environment values."""
        self._config = None
        return self.load()

    def _resolve_config_dir(self, config_dir: str | Path | None) -> Path:
        if config_dir is not None:
            return Path(config_dir).expanduser().resolve()

        configured_dir = os.getenv(f"{self._env_prefix}CONFIG_DIR")
        if configured_dir:
            return Path(configured_dir).expanduser().resolve()

        project_dir = Path(__file__).resolve().parents[2]
        return (project_dir / DEFAULT_CONFIG_DIRECTORY).resolve()

    def _selected_environment(self) -> str:
        profile = self._environment or os.getenv(
            f"{self._env_prefix}ENV", "default"
        )
        profile = profile.strip()
        if not profile or not PROFILE_NAME_PATTERN.fullmatch(profile):
            raise ValueError(f"invalid configuration environment: {profile!r}")
        return profile

    def _profile_file(self, profile: str) -> Path:
        return self._config_dir / f"{profile}.yaml"

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise FileNotFoundError(f"configuration file not found: {path}")

        with path.open("r", encoding="utf-8") as stream:
            loaded = yaml.safe_load(stream)

        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ValueError(f"configuration root must be a mapping: {path}")
        return loaded

    @classmethod
    def _deep_merge(
        cls, base: Mapping[str, Any], override: Mapping[str, Any]
    ) -> dict[str, Any]:
        result = deepcopy(dict(base))
        for key, value in override.items():
            if isinstance(result.get(key), Mapping) and isinstance(value, Mapping):
                result[key] = cls._deep_merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    def _apply_environment_overrides(self, data: dict[str, Any]) -> None:
        valid_paths = self._model_leaf_paths(AppConfig)
        prefix_length = len(self._env_prefix)

        for env_name, raw_value in os.environ.items():
            normalized_name = env_name.upper()
            if not normalized_name.startswith(self._env_prefix):
                continue

            path_key = normalized_name[prefix_length:]
            path = tuple(part.lower() for part in path_key.split("__"))
            if path not in valid_paths:
                continue

            self._set_nested(data, path, yaml.safe_load(raw_value))

    @classmethod
    def _model_leaf_paths(
        cls,
        model: type[BaseModel],
        prefix: tuple[str, ...] = (),
    ) -> set[tuple[str, ...]]:
        paths: set[tuple[str, ...]] = set()
        for field_name, field in model.model_fields.items():
            field_path = (*prefix, field_name)
            annotation = field.annotation
            if isinstance(annotation, type) and issubclass(annotation, BaseModel):
                paths.update(cls._model_leaf_paths(annotation, field_path))
            else:
                paths.add(field_path)
        return paths

    @staticmethod
    def _set_nested(
        data: dict[str, Any], path: tuple[str, ...], value: Any
    ) -> None:
        current = data
        for part in path[:-1]:
            nested = current.get(part)
            if not isinstance(nested, dict):
                nested = {}
                current[part] = nested
            current = nested
        current[path[-1]] = value
