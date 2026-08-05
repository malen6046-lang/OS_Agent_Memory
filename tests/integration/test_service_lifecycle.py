import pytest
from tests.asgi_client import ASGITestClient

from app.dependencies import (
    FallbackEmbeddingProvider,
    FallbackVectorStoreAdapter,
    ServiceStartupError,
)
from app.main import app


def test_lifespan_starts_reuses_and_closes_application_services():
    with ASGITestClient(app) as client:
        container = app.state.service_container
        service = app.state.api_service

        assert container.embedding_provider.started is True
        assert container.vector_store.started is True
        assert service is app.state.api_service
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/api/v1/health").status_code == 200
        assert service is app.state.api_service

    assert container.vector_store.closed is True
    assert container.embedding_provider.closed is True
    assert container.vector_store.lifecycle_events == [
        "vector.start",
        "vector.close",
    ]
    assert container.embedding_provider.lifecycle_events == [
        "embedding.start",
        "embedding.close",
    ]


def test_lifespan_uses_fallback_providers_from_environment(monkeypatch):
    monkeypatch.setenv("OS_AGENT_EMBEDDING__PROVIDER", "fallback")
    monkeypatch.setenv("OS_AGENT_VECTOR_STORE__PROVIDER", "fallback")

    with ASGITestClient(app):
        container = app.state.service_container
        assert isinstance(
            container.embedding_provider, FallbackEmbeddingProvider
        )
        assert isinstance(
            container.vector_store, FallbackVectorStoreAdapter
        )


def test_lifespan_real_mode_uses_built_in_algorithms(monkeypatch):
    monkeypatch.setenv("OS_AGENT_SERVICES__MODE", "real")

    with ASGITestClient(app):
        container = app.state.service_container
        assert container.mode == "real"
        assert type(container.knowledge_service).__name__ == "AsyncKnowledgeServiceAdapter"
        assert type(container.retriever).__name__ == "AsyncHybridRetrieverAdapter"


def test_lifespan_fails_when_kylin_provider_is_missing(monkeypatch):
    monkeypatch.setenv("OS_AGENT_EMBEDDING__PROVIDER", "kylin")

    with pytest.raises(
        ServiceStartupError,
        match="Kylin EmbeddingProvider real implementation is not configured",
    ):
        with ASGITestClient(app):
            pass
