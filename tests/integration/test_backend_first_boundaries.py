"""Architecture gates for the backend-first integration stage."""

from __future__ import annotations

import ast
import asyncio
import os
from pathlib import Path

import pytest

from app.core.config import ConfigManager
from app.dependencies import (
    MockAuditRepository,
    MockEmbeddingProvider,
    MockEvaluationService,
    MockForgetService,
    MockIdempotencyRepository,
    MockKnowledgeService,
    MockMemoryRepository,
    MockPreferenceService,
    MockRetriever,
    MockSafetyService,
    MockVectorStoreAdapter,
    build_service_container,
)
from app.main import app


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_API_ROUTES = {
    ("GET", "/api/v1/health"),
    ("POST", "/api/v1/events/ingest"),
    ("POST", "/api/v1/memory/search"),
    ("POST", "/api/v1/forget/preview"),
    ("POST", "/api/v1/forget/execute"),
    ("POST", "/api/v1/evaluations/run"),
}
PREFERENCE_SAFETY_OVERRIDES = {
    "preference_implementation": (
        "adapters.preference_safety.preference:build_preference_service"
    ),
    "safety_implementation": (
        "adapters.preference_safety.safety:build_safety_service"
    ),
    "forget_implementation": (
        "adapters.preference_safety.forget:build_forget_service"
    ),
}
ALGORITHM_MODULE_OVERRIDES = {
    **PREFERENCE_SAFETY_OVERRIDES,
    "knowledge_implementation": (
        "adapters.knowledge_retrieval.knowledge:build_knowledge_service"
    ),
    "retriever_implementation": (
        "adapters.knowledge_retrieval.retrieval:build_hybrid_retriever"
    ),
}


def _static_import_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.partition(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                roots.add(node.module.partition(".")[0])
            else:
                roots.update(alias.name.partition(".")[0] for alias in node.names)
    return roots


def _violations(paths: list[Path], forbidden: set[str]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for path in paths:
        imports = sorted(_static_import_roots(path) & forbidden)
        if imports:
            found[path.relative_to(PROJECT_ROOT).as_posix()] = imports
    return found


def _clear_os_agent_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in list(os.environ):
        if name.upper().startswith("OS_AGENT_"):
            monkeypatch.delenv(name)


def test_backend_stage_keeps_the_six_frozen_api_routes() -> None:
    paths = app.openapi()["paths"]
    registered = {
        (method.upper(), path)
        for path, operations in paths.items()
        if path.startswith("/api/v1/")
        for method in operations
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    assert registered == EXPECTED_API_ROUTES


def test_api_layer_does_not_import_repositories_or_algorithm_modules() -> None:
    api_files = sorted((PROJECT_ROOT / "app" / "api").rglob("*.py"))
    api_files.append(PROJECT_ROOT / "app" / "dependencies" / "api_service.py")

    assert _violations(api_files, {"repositories", "modules"}) == {}


@pytest.mark.parametrize("profile", ["default", "development"])
def test_default_and_development_assembly_stay_algorithm_free(
    profile: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency_files = sorted(
        (PROJECT_ROOT / "app" / "dependencies").rglob("*.py")
    )
    composition_files = [PROJECT_ROOT / "app" / "main.py", *dependency_files]
    assert _violations(composition_files, {"modules"}) == {}

    _clear_os_agent_environment(monkeypatch)

    container = build_service_container(ConfigManager().load(profile))
    assembled_components = {
        "preference_service": container.preference_service,
        "safety_service": container.safety_service,
        "forget_service": container.forget_service,
        "knowledge_service": container.knowledge_service,
        "retriever": container.retriever,
        "embedding_provider": container.embedding_provider,
        "vector_store": container.vector_store,
    }
    algorithm_components = {
        name: type(component).__module__
        for name, component in assembled_components.items()
        if type(component).__module__.partition(".")[0] == "modules"
    }
    assert algorithm_components == {}


def test_preference_safety_profile_changes_only_three_service_factories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_os_agent_environment(monkeypatch)
    baseline = ConfigManager().load("default").model_dump(mode="python")
    configured = ConfigManager().load("preference_safety").model_dump(
        mode="python"
    )

    baseline["services"].update(PREFERENCE_SAFETY_OVERRIDES)

    assert configured == baseline
    assert configured["services"]["mode"] == "mock"


def test_preference_safety_profile_builds_and_starts_hybrid_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_os_agent_environment(monkeypatch)
    container = build_service_container(
        ConfigManager().load("preference_safety")
    )

    assert not isinstance(container.preference_service, MockPreferenceService)
    assert not isinstance(container.safety_service, MockSafetyService)
    assert not isinstance(container.forget_service, MockForgetService)
    assert isinstance(container.knowledge_service, MockKnowledgeService)
    assert isinstance(container.retriever, MockRetriever)
    assert isinstance(container.embedding_provider, MockEmbeddingProvider)
    assert isinstance(container.vector_store, MockVectorStoreAdapter)
    assert isinstance(container.memory_repository, MockMemoryRepository)
    assert isinstance(
        container.idempotency_repository, MockIdempotencyRepository
    )
    assert isinstance(container.audit_repository, MockAuditRepository)
    assert isinstance(container.evaluation_service, MockEvaluationService)

    async def exercise_lifecycle() -> None:
        await container.start()
        try:
            assert container.embedding_provider.started is True
            assert container.vector_store.started is True
        finally:
            await container.close()

    asyncio.run(exercise_lifecycle())

    assert container.embedding_provider.closed is True
    assert container.vector_store.closed is True


def test_algorithm_modules_profile_changes_only_five_service_factories(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_os_agent_environment(monkeypatch)
    baseline = ConfigManager().load("default").model_dump(mode="python")
    configured = ConfigManager().load("algorithm_modules").model_dump(
        mode="python"
    )

    baseline["services"].update(ALGORITHM_MODULE_OVERRIDES)

    assert configured == baseline
    assert configured["services"]["mode"] == "mock"


def test_algorithm_modules_profile_builds_only_configured_algorithm_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_os_agent_environment(monkeypatch)
    container = build_service_container(
        ConfigManager().load("algorithm_modules")
    )

    assert not isinstance(container.preference_service, MockPreferenceService)
    assert not isinstance(container.safety_service, MockSafetyService)
    assert not isinstance(container.forget_service, MockForgetService)
    assert not isinstance(container.knowledge_service, MockKnowledgeService)
    assert not isinstance(container.retriever, MockRetriever)
    assert isinstance(container.embedding_provider, MockEmbeddingProvider)
    assert isinstance(container.vector_store, MockVectorStoreAdapter)
    assert isinstance(container.memory_repository, MockMemoryRepository)
    assert isinstance(
        container.idempotency_repository, MockIdempotencyRepository
    )
    assert isinstance(container.audit_repository, MockAuditRepository)
    assert isinstance(container.evaluation_service, MockEvaluationService)

    async def exercise_lifecycle() -> None:
        await container.start()
        try:
            assert container.embedding_provider.started is True
            assert container.vector_store.started is True
        finally:
            await container.close()

    asyncio.run(exercise_lifecycle())

    assert container.embedding_provider.closed is True
    assert container.vector_store.closed is True
