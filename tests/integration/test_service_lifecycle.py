import pytest
from fastapi.testclient import TestClient

from app.dependencies import (
    FallbackEmbeddingProvider,
    FallbackVectorStoreAdapter,
    ServiceStartupError,
)
from app.main import app


def test_lifespan_starts_reuses_and_closes_application_services():
    with TestClient(app) as client:
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

    with TestClient(app):
        container = app.state.service_container
        assert isinstance(
            container.embedding_provider, FallbackEmbeddingProvider
        )
        assert isinstance(
            container.vector_store, FallbackVectorStoreAdapter
        )


def test_lifespan_fails_when_real_service_is_missing(monkeypatch):
    monkeypatch.setenv("OS_AGENT_SERVICES__MODE", "real")

    with pytest.raises(
        ServiceStartupError,
        match="MemoryRepository real implementation is not configured",
    ):
        with TestClient(app):
            pass


def test_lifespan_fails_when_kylin_provider_is_missing(monkeypatch):
    monkeypatch.setenv("OS_AGENT_EMBEDDING__PROVIDER", "kylin")

    with pytest.raises(
        ServiceStartupError,
        match="Kylin EmbeddingProvider real implementation is not configured",
    ):
        with TestClient(app):
            pass
