import asyncio
import sys
from types import ModuleType

import pytest

from app.core.config import ConfigManager
from app.dependencies import (
    FallbackEmbeddingProvider,
    FallbackVectorStoreAdapter,
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
    ServiceContainer,
    ServiceStartupError,
    build_service_container,
    get_memory_orchestrator,
)
from contracts.schemas.provider import VectorStoreConfig
from repositories import (
    SQLiteAuditRepository,
    SQLiteIdempotencyRepository,
    SQLiteMemoryRepository,
)


def run(coroutine):
    return asyncio.run(coroutine)


def test_mock_configuration_registers_every_required_singleton():
    container = build_service_container(ConfigManager().load("default"))

    assert isinstance(container.preference_service, MockPreferenceService)
    assert isinstance(container.safety_service, MockSafetyService)
    assert isinstance(container.forget_service, MockForgetService)
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
    assert container.retriever.embedding_provider is container.embedding_provider
    assert container.retriever.vector_store is container.vector_store
    assert container.retriever.memory_repository is container.memory_repository


def test_development_profile_selects_fallback_providers():
    container = build_service_container(ConfigManager().load("development"))

    assert isinstance(container.preference_service, MockPreferenceService)
    assert isinstance(container.safety_service, MockSafetyService)
    assert isinstance(container.forget_service, MockForgetService)
    assert isinstance(container.knowledge_service, MockKnowledgeService)
    assert isinstance(container.retriever, MockRetriever)
    assert isinstance(container.embedding_provider, FallbackEmbeddingProvider)
    assert isinstance(container.vector_store, FallbackVectorStoreAdapter)
    assert isinstance(container.memory_repository, SQLiteMemoryRepository)
    assert isinstance(
        container.idempotency_repository,
        SQLiteIdempotencyRepository,
    )
    assert isinstance(container.audit_repository, SQLiteAuditRepository)


def test_mock_mode_can_override_only_preference_safety_and_forget(
    monkeypatch,
):
    module = ModuleType("test_preference_safety_factories")

    class PreferenceOverride:
        def __init__(self, config):
            self.config = config

    class SafetyOverride:
        def __init__(self, config):
            self.config = config

    class ForgetOverride:
        def __init__(self, config):
            self.config = config

    module.PreferenceOverride = PreferenceOverride
    module.SafetyOverride = SafetyOverride
    module.ForgetOverride = ForgetOverride
    monkeypatch.setitem(sys.modules, module.__name__, module)

    base = ConfigManager().load("default")
    services = base.services.model_copy(
        update={
            "preference_implementation": (
                f"{module.__name__}:PreferenceOverride"
            ),
            "safety_implementation": f"{module.__name__}:SafetyOverride",
            "forget_implementation": f"{module.__name__}:ForgetOverride",
        }
    )
    config = base.model_copy(update={"services": services})

    container = build_service_container(config)

    assert container.mode == "mock"
    assert isinstance(container.preference_service, PreferenceOverride)
    assert isinstance(container.safety_service, SafetyOverride)
    assert isinstance(container.forget_service, ForgetOverride)
    assert container.preference_service.config is config
    assert container.safety_service.config is config
    assert container.forget_service.config is config
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


def test_mock_mode_builds_configured_algorithm_graph_in_dependency_order(
    monkeypatch,
):
    module = ModuleType("test_algorithm_graph_factories")
    events = []

    class KnowledgeOverride:
        pass

    class RetrieverOverride:
        pass

    class ForgetOverride:
        pass

    def build_knowledge_service(
        embedding_provider,
        vector_store,
        memory_repository,
        config,
        app_config,
    ):
        events.append("knowledge")
        service = KnowledgeOverride()
        service.dependencies = (
            embedding_provider,
            vector_store,
            memory_repository,
            config,
            app_config,
        )
        return service

    def build_hybrid_retriever(
        knowledge_service,
        embedding_provider,
        vector_store,
        memory_repository,
    ):
        events.append("retriever")
        service = RetrieverOverride()
        service.dependencies = (
            knowledge_service,
            embedding_provider,
            vector_store,
            memory_repository,
        )
        return service

    def build_forget_service(retriever):
        events.append("forget")
        service = ForgetOverride()
        service.retriever = retriever
        return service

    module.build_knowledge_service = build_knowledge_service
    module.build_hybrid_retriever = build_hybrid_retriever
    module.build_forget_service = build_forget_service
    monkeypatch.setitem(sys.modules, module.__name__, module)

    base = ConfigManager().load("default")
    services = base.services.model_copy(
        update={
            "knowledge_implementation": (
                f"{module.__name__}:build_knowledge_service"
            ),
            "retriever_implementation": (
                f"{module.__name__}:build_hybrid_retriever"
            ),
            "forget_implementation": (
                f"{module.__name__}:build_forget_service"
            ),
        }
    )
    config = base.model_copy(update={"services": services})

    container = build_service_container(config)

    assert events == ["knowledge", "retriever", "forget"]
    assert isinstance(container.knowledge_service, KnowledgeOverride)
    assert isinstance(container.retriever, RetrieverOverride)
    assert isinstance(container.forget_service, ForgetOverride)
    assert container.knowledge_service.dependencies == (
        container.embedding_provider,
        container.vector_store,
        container.memory_repository,
        config.retrieval,
        config,
    )
    assert container.retriever.dependencies == (
        container.knowledge_service,
        container.embedding_provider,
        container.vector_store,
        container.memory_repository,
    )
    assert container.forget_service.retriever is container.retriever
    assert isinstance(container.preference_service, MockPreferenceService)
    assert isinstance(container.safety_service, MockSafetyService)
    assert isinstance(container.evaluation_service, MockEvaluationService)


def test_environment_can_switch_service_and_provider_configuration(
    monkeypatch,
):
    monkeypatch.setenv("OS_AGENT_SERVICES__MODE", "mock")
    monkeypatch.setenv("OS_AGENT_EMBEDDING__PROVIDER", "fallback")
    monkeypatch.setenv("OS_AGENT_VECTOR_STORE__PROVIDER", "fallback")

    config = ConfigManager().load()
    container = build_service_container(config)

    assert config.services.mode == "mock"
    assert isinstance(container.embedding_provider, FallbackEmbeddingProvider)
    assert isinstance(container.vector_store, FallbackVectorStoreAdapter)


def test_real_mode_loads_each_explicitly_configured_factory():
    base = ConfigManager().load()
    services = base.services.model_copy(
        update={
            "mode": "real",
            "preference_implementation": (
                "app.dependencies.mock_services:MockPreferenceService"
            ),
            "safety_implementation": (
                "app.dependencies.mock_services:MockSafetyService"
            ),
            "forget_implementation": (
                "app.dependencies.mock_services:MockForgetService"
            ),
            "knowledge_implementation": (
                "app.dependencies.mock_services:MockKnowledgeService"
            ),
            "retriever_implementation": (
                "app.dependencies.mock_services:MockRetriever"
            ),
            "memory_repository_implementation": (
                "app.dependencies.mock_services:MockMemoryRepository"
            ),
            "idempotency_repository_implementation": (
                "app.dependencies.mock_services:MockIdempotencyRepository"
            ),
            "audit_repository_implementation": (
                "app.dependencies.mock_services:MockAuditRepository"
            ),
            "evaluation_implementation": (
                "app.dependencies.mock_services:MockEvaluationService"
            ),
        }
    )

    container = build_service_container(
        base.model_copy(update={"services": services})
    )

    assert container.mode == "real"
    assert isinstance(container.preference_service, MockPreferenceService)
    assert isinstance(container.safety_service, MockSafetyService)
    assert isinstance(container.forget_service, MockForgetService)
    assert isinstance(container.knowledge_service, MockKnowledgeService)
    assert isinstance(container.hybrid_retriever, MockRetriever)
    assert (
        container.hybrid_retriever.memory_repository
        is container.memory_repository
    )
    assert container.vector_store_adapter is container.vector_store


def test_real_mode_without_repository_implementation_has_explicit_error():
    config = ConfigManager().load().model_copy(
        update={
            "services": ConfigManager().load().services.model_copy(
                update={"mode": "real"}
            )
        }
    )

    with pytest.raises(
        ServiceStartupError,
        match="MemoryRepository real implementation is not configured",
    ):
        build_service_container(config)


def test_kylin_provider_without_implementation_has_explicit_error():
    base = ConfigManager().load()
    config = base.model_copy(
        update={
            "embedding": base.embedding.model_copy(
                update={"provider": "kylin", "implementation": None}
            )
        }
    )

    with pytest.raises(
        ServiceStartupError,
        match="Kylin EmbeddingProvider real implementation is not configured",
    ):
        build_service_container(config)


def test_provider_lifecycle_uses_dependency_order_and_reverse_shutdown():
    events = []

    class EmbeddingSpy:
        def start(self):
            events.append("embedding.start")

        def close(self):
            events.append("embedding.close")

    class VectorSpy:
        def start(self, config):
            assert config.provider == "memory"
            events.append("vector.start")

        def close(self):
            events.append("vector.close")

    container = ServiceContainer(
        MockPreferenceService(),
        MockKnowledgeService(),
        MockRetriever(),
        MockForgetService(),
        safety_service=MockSafetyService(),
        embedding_provider=EmbeddingSpy(),
        vector_store=VectorSpy(),
        vector_store_config=VectorStoreConfig(
            provider="memory",
            collection_name="test",
            expected_dimension=1,
        ),
    )

    run(container.start())
    run(container.start())
    run(container.close())

    assert events == [
        "embedding.start",
        "vector.start",
        "vector.close",
        "embedding.close",
    ]


def test_failed_vector_start_closes_already_started_embedding():
    events = []

    class EmbeddingSpy:
        def start(self):
            events.append("embedding.start")

        def close(self):
            events.append("embedding.close")

    class FailingVector:
        def start(self, config):
            events.append("vector.start")
            raise RuntimeError("vector unavailable")

        def close(self):
            events.append("vector.close")

    container = ServiceContainer(
        MockPreferenceService(),
        MockKnowledgeService(),
        MockRetriever(),
        MockForgetService(),
        embedding_provider=EmbeddingSpy(),
        vector_store=FailingVector(),
        vector_store_config=VectorStoreConfig(
            provider="memory",
            collection_name="test",
            expected_dimension=1,
        ),
    )

    with pytest.raises(ServiceStartupError, match="vector unavailable"):
        run(container.start())

    assert events == [
        "embedding.start",
        "vector.start",
        "embedding.close",
    ]


def test_orchestrator_receives_container_singletons():
    container = build_service_container(ConfigManager().load())

    orchestrator = get_memory_orchestrator(container)

    assert orchestrator._preference_service is container.preference_service
    assert orchestrator._knowledge_service is container.knowledge_service
    assert orchestrator._retriever is container.retriever
    assert orchestrator._forget_service is container.forget_service
    assert orchestrator._repository is container.memory_repository
    assert (
        orchestrator._idempotency_repository
        is container.idempotency_repository
    )
    assert orchestrator._audit_repository is container.audit_repository
    assert orchestrator._evaluation_service is container.evaluation_service
