import asyncio

import pytest

from app.core.config import ConfigManager, VectorStoreConfig
from app.dependencies import (
    FallbackEmbeddingProvider,
    FallbackVectorStoreAdapter,
    MockEmbeddingProvider,
    MockForgetService,
    MockKnowledgeService,
    MockPreferenceService,
    MockRetriever,
    MockSafetyService,
    MockVectorStoreAdapter,
    ServiceContainer,
    ServiceStartupError,
    build_service_container,
    get_memory_orchestrator,
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
    assert container.retriever.embedding_provider is container.embedding_provider
    assert container.retriever.vector_store is container.vector_store


def test_development_profile_selects_real_algorithm_with_mvp_providers():
    container = build_service_container(ConfigManager().load("development"))

    assert container.mode == "real"
    assert type(container.embedding_provider).__name__ == "MockEmbeddingProvider"
    assert type(container.vector_store).__name__ == "MemoryVectorStore"


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
    assert container.vector_store_adapter is container.vector_store


def test_real_service_without_external_implementation_uses_built_in_algorithms():
    config = ConfigManager().load().model_copy(
        update={
            "services": ConfigManager().load().services.model_copy(
                update={"mode": "real"}
            )
        }
    )

    container = build_service_container(config)
    assert container.mode == "real"
    assert type(container.knowledge_service).__name__ == "AsyncKnowledgeServiceAdapter"
    assert type(container.retriever).__name__ == "AsyncHybridRetrieverAdapter"


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
            assert config.provider == "mock"
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
        vector_store_config=VectorStoreConfig(provider="mock"),
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
        vector_store_config=VectorStoreConfig(provider="mock"),
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
