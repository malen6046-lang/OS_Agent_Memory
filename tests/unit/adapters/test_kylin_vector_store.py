"""Tests for the V1.2.2 Kylin VectorStoreAdapter."""

import pytest

from adapters.vector_store.kylin_vector_store import KylinVectorStoreAdapter
from contracts.schemas.common import MemoryStatus
from contracts.schemas.provider import (
    CollectionSpec,
    DeleteResult,
    ProviderHealth,
    UpsertResult,
    VectorHit,
    VectorItem,
    VectorQuery,
    VectorStoreConfig,
)


class FakeVectorClient:
    def __init__(self):
        self.closed = False
        self.collection = None
        self.items = []

    def vector_start(self, config):
        return {
            "status": "ready",
            "database_path": "/tmp/test.db",
            "collection_name": config["collection_name"],
            "dimension": config["expected_dimension"],
            "metric": config["metric"],
        }

    def health(self):
        return {"status": "ready", "vector_status": "ready"}

    def vector_close(self):
        self.closed = True
        return {"status": "stopped"}

    def ensure_collection(self, spec):
        self.collection = spec
        return {"created": True, **spec}

    def vector_upsert(self, items):
        self.items = items
        return {"upserted": len(items)}

    def vector_query(self, request):
        return {
            "hits": [
                {
                    "vector_pk": 7,
                    "memory_id": "mem-7",
                    "user_id": request["user_id"],
                    "status": request["status"],
                    "score": 0.9,
                }
            ],
            "elapsed_ms": 2,
        }

    def vector_delete(self, vector_pks):
        return {
            "deleted": 1 if 7 in vector_pks else 0,
            "missing_vector_pks": [pk for pk in vector_pks if pk != 7],
        }


def config():
    return VectorStoreConfig(
        provider="kylin",
        collection_name="test_collection",
        expected_dimension=3,
        metric="cosine",
    )


def started_adapter():
    client = FakeVectorClient()
    adapter = KylinVectorStoreAdapter(client=client)
    health = adapter.start(config())
    return adapter, client, health


def test_start_returns_frozen_provider_health():
    _, _, health = started_adapter()
    assert isinstance(health, ProviderHealth)
    assert health.status == "ok"
    assert health.details["dimension"] == 3


def test_ensure_collection_uses_frozen_spec():
    adapter, client, _ = started_adapter()
    adapter.ensure_collection(
        CollectionSpec(name="test_collection", dimension=3, metric="cosine")
    )
    assert client.collection["name"] == "test_collection"


def test_upsert_returns_frozen_result_and_identity_metadata():
    adapter, client, _ = started_adapter()
    result = adapter.upsert(
        [
            VectorItem(
                vector_pk=7,
                memory_id="mem-7",
                user_id="user-1",
                status=MemoryStatus.ACTIVE,
                vector=[0.1, 0.2, 0.3],
                metadata={"kind": "preference"},
            )
        ]
    )
    assert isinstance(result, UpsertResult)
    assert result.upserted == 1
    assert client.items[0]["memory_id"] == "mem-7"


def test_query_returns_frozen_vector_hits():
    adapter, _, _ = started_adapter()
    hits = adapter.query(
        VectorQuery(
            user_id="user-1",
            status=MemoryStatus.ACTIVE,
            vector=[0.1, 0.2, 0.3],
            top_k=5,
            timeout_ms=500,
        )
    )
    assert len(hits) == 1
    assert isinstance(hits[0], VectorHit)
    assert hits[0].user_id == "user-1"


def test_delete_reports_missing_ids_with_frozen_result():
    adapter, _, _ = started_adapter()
    result = adapter.delete([7, 8])
    assert isinstance(result, DeleteResult)
    assert result.deleted == 1
    assert result.missing_vector_pks == [8]


def test_operations_require_start():
    adapter = KylinVectorStoreAdapter(client=FakeVectorClient())
    with pytest.raises(RuntimeError, match="not started"):
        adapter.delete([7])


def test_dimension_mismatch_is_rejected_before_sidecar_call():
    adapter, _, _ = started_adapter()
    with pytest.raises(ValueError, match="dimension mismatch"):
        adapter.upsert(
            [
                VectorItem(
                    vector_pk=7,
                    memory_id="mem-7",
                    user_id="user-1",
                    status=MemoryStatus.ACTIVE,
                    vector=[0.1],
                )
            ]
        )


def test_close_calls_vector_close_and_resets_lifecycle():
    adapter, client, _ = started_adapter()
    adapter.close()
    assert client.closed is True
    with pytest.raises(RuntimeError, match="not started"):
        adapter.query(
            VectorQuery(
                user_id="user-1",
                vector=[0.1, 0.2, 0.3],
                top_k=1,
                timeout_ms=500,
            )
        )


def test_health_reports_ready_vector_sidecar():
    adapter, _, _ = started_adapter()
    health = adapter.health()
    assert isinstance(health, ProviderHealth)
    assert health.status == "ok"
