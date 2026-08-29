"""Tests for the V1.2.2 Kylin EmbeddingProvider adapter."""

from __future__ import annotations

import pytest

from adapters.embedding.kylin_provider import KylinEmbeddingProvider
from adapters.embedding.kylin_sidecar_client import KylinSidecarTransportError
from contracts.schemas.provider import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderHealth,
)


class FakeSidecarClient:
    def __init__(self, dimension: int = 3) -> None:
        self.dimension = dimension
        self.health_status = "ready"
        self.fail_health = False

    def health(self):
        if self.fail_health:
            raise KylinSidecarTransportError("offline")
        return {
            "status": self.health_status,
            "provider": "kylin-ai-runtime",
            "model": "test-model",
            "model_version": "1",
            "space_id": f"kylin-ai-runtime:test-model:1:{self.dimension}",
            "dimension": self.dimension,
        }

    def model_info(self):
        return {
            "provider": "kylin-ai-runtime",
            "model": "test-model",
            "model_version": "1",
            "space_id": f"kylin-ai-runtime:test-model:1:{self.dimension}",
            "dimension": self.dimension,
        }

    def encode(self, texts):
        return {
            "provider": "kylin-ai-runtime",
            "model": "test-model",
            "model_version": "1",
            "space_id": f"kylin-ai-runtime:test-model:1:{self.dimension}",
            "dimension": self.dimension,
            "vectors": [
                [float(index + 1)] * self.dimension for index, _ in enumerate(texts)
            ],
            "elapsed_ms": len(texts),
            "item_elapsed_ms": [1] * len(texts),
        }


def test_start_returns_frozen_health_and_model_schemas():
    provider = KylinEmbeddingProvider(
        model_name="test-model", client=FakeSidecarClient()
    )

    health = provider.start()
    model = provider.model_info()

    assert isinstance(health, ProviderHealth)
    assert health.status == "ok"
    assert isinstance(model, EmbeddingModelInfo)
    assert model.model_name == "test-model"
    assert model.dimension == 3


def test_encode_returns_frozen_embedding_batch_schema():
    provider = KylinEmbeddingProvider(client=FakeSidecarClient())
    provider.start()

    batch = provider.encode(["first", "second"])

    assert isinstance(batch, EmbeddingBatch)
    assert len(batch.vectors) == 2
    assert all(len(vector) == 3 for vector in batch.vectors)


def test_encode_requires_provider_start():
    provider = KylinEmbeddingProvider(client=FakeSidecarClient())

    with pytest.raises(RuntimeError, match="not started"):
        provider.encode(["text"])


def test_encode_rejects_empty_text_item():
    provider = KylinEmbeddingProvider(client=FakeSidecarClient())
    provider.start()

    with pytest.raises(ValueError, match="non-empty strings"):
        provider.encode([""])


def test_empty_batch_does_not_call_sidecar_and_remains_schema_valid():
    provider = KylinEmbeddingProvider(client=FakeSidecarClient())
    provider.start()

    batch = provider.encode([])

    assert batch.vectors == []
    assert batch.dimension == 3


def test_explicit_model_mismatch_fails_startup():
    provider = KylinEmbeddingProvider(
        model_name="different-model", client=FakeSidecarClient()
    )

    with pytest.raises(RuntimeError, match="model mismatch"):
        provider.start()


def test_close_changes_health_to_stopped_without_stopping_sidecar():
    client = FakeSidecarClient()
    provider = KylinEmbeddingProvider(client=client)
    provider.start()

    provider.close()

    assert provider.health().status == "stopped"


def test_deep_health_reports_transport_failure_as_unavailable():
    client = FakeSidecarClient()
    provider = KylinEmbeddingProvider(client=client)
    provider.start()
    client.fail_health = True

    health = provider.health(deep=True)

    assert health.status == "unavailable"
    assert "offline" in health.details["error"]
