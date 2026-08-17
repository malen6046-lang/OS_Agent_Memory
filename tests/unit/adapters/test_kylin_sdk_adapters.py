from __future__ import annotations

import ctypes

import pytest

from adapters.embedding.kylin_provider import (
    KylinEmbeddingError,
    KylinEmbeddingProvider,
)
from adapters.vector_store.kylin_vector_store import KylinVectorStoreAdapter
from contracts.schemas.common import MemoryStatus
from contracts.schemas.provider import (
    CollectionSpec,
    VectorItem,
    VectorQuery,
    VectorStoreConfig,
)


class FakeEmbeddingNative:
    def __init__(self, *, dimension: int = 4) -> None:
        self.dimension = dimension
        self.destroyed = False
        self.initialized_model: str | None = None
        self.encoded: list[str] = []

    def create_session(self) -> ctypes.c_void_p:
        return ctypes.c_void_p(11)

    def destroy_session(self, session: ctypes.c_void_p) -> None:
        assert session.value == 11
        self.destroyed = True

    def init_session(self, session: ctypes.c_void_p) -> int:
        assert session.value == 11
        return 0

    def enable_internal_event_loop(
        self, session: ctypes.c_void_p, enabled: bool
    ) -> None:
        assert session.value == 11
        assert enabled is False

    def models(self, session: ctypes.c_void_p) -> list[tuple[str, int]]:
        assert session.value == 11
        return [("other", 8), ("configured-model", self.dimension)]

    def init_model(self, session: ctypes.c_void_p, model_name: str) -> int:
        assert session.value == 11
        self.initialized_model = model_name
        return 0

    def encode(self, session: ctypes.c_void_p, text: str) -> list[float]:
        assert session.value == 11
        self.encoded.append(text)
        return [float(len(text))] * self.dimension


class FakeVectorNative:
    def __init__(self) -> None:
        self.closed = False
        self.opened: dict | None = None
        self.collection: tuple[str, int, str] | None = None
        self.items: dict[int, VectorItem] = {}

    def open(self, app_id, db_file, encrypt, key, timeout_ms):
        self.opened = {
            "app_id": app_id,
            "db_file": db_file,
            "encrypt": encrypt,
            "key": key,
            "timeout_ms": timeout_ms,
        }
        return ctypes.c_void_p(22)

    def close(self, handle):
        assert handle.value == 22
        self.closed = True

    def ensure_collection(self, handle, name, dimension, metric):
        assert handle.value == 22
        self.collection = (name, dimension, metric)

    def upsert(self, handle, collection, items, dimension):
        assert handle.value == 22
        assert self.collection == (collection, dimension, "cosine")
        for item in items:
            self.items[item.vector_pk] = item
        return len(items)

    def query(self, handle, collection, request, metric):
        assert handle.value == 22
        assert collection == "memory"
        assert metric == "cosine"
        results = []
        for item in self.items.values():
            if item.user_id != request.user_id or item.status != request.status:
                continue
            results.append(
                {
                    "vector_pk": item.vector_pk,
                    "memory_id": item.memory_id,
                    "user_id": item.user_id,
                    "status": item.status.value,
                    "score": 0.9,
                    "metadata": item.metadata,
                }
            )
        return results

    def delete(self, handle, collection, vector_pks):
        assert handle.value == 22
        assert collection == "memory"
        deleted = []
        for vector_pk in vector_pks:
            if self.items.pop(vector_pk, None) is not None:
                deleted.append(vector_pk)
        return deleted


def test_embedding_selects_configured_model_and_returns_contract() -> None:
    native = FakeEmbeddingNative(dimension=4)
    provider = KylinEmbeddingProvider(
        model_name="configured-model",
        expected_dimension=4,
        native=native,
    )

    health = provider.start()
    batch = provider.encode(["麒麟", "memory"])

    assert health.provider == "kylin"
    assert health.status == "ok"
    assert native.initialized_model == "configured-model"
    assert native.encoded[0] == "OS Agent memory embedding warmup"
    assert batch.dimension == 4
    assert len(batch.vectors) == 2
    assert provider.model_info().model_fingerprint
    provider.close()
    assert native.destroyed is True


def test_embedding_rejects_dimension_mismatch_and_destroys_session() -> None:
    native = FakeEmbeddingNative(dimension=5)
    provider = KylinEmbeddingProvider(
        model_name="configured-model",
        expected_dimension=4,
        native=native,
    )

    with pytest.raises(KylinEmbeddingError, match="expected 4, got 5"):
        provider.start()

    assert native.destroyed is True


def test_embedding_rejects_blank_input_before_native_call() -> None:
    native = FakeEmbeddingNative(dimension=4)
    provider = KylinEmbeddingProvider(
        model_name="configured-model",
        expected_dimension=4,
        native=native,
    )
    provider.start()

    with pytest.raises(ValueError, match="non-empty"):
        provider.encode([" "])

    assert native.encoded == ["OS Agent memory embedding warmup"]


def test_embedding_warmup_can_be_disabled() -> None:
    native = FakeEmbeddingNative(dimension=4)
    provider = KylinEmbeddingProvider(
        model_name="configured-model",
        expected_dimension=4,
        warmup=False,
        native=native,
    )

    health = provider.start()

    assert native.encoded == []
    assert health.details["warmed_up"] is False


def _vector_item(
    vector_pk: int,
    *,
    user_id: str = "user-1",
    status: MemoryStatus = MemoryStatus.ACTIVE,
    scene: str = "desktop",
) -> VectorItem:
    return VectorItem(
        vector_pk=vector_pk,
        memory_id=f"memory-{vector_pk}",
        user_id=user_id,
        status=status,
        vector=[0.1, 0.2, 0.3, 0.4],
        metadata={"scene": scene},
    )


def test_vector_adapter_round_trip_filters_and_precise_delete(tmp_path) -> None:
    native = FakeVectorNative()
    adapter = KylinVectorStoreAdapter(
        native=native,
        db_file=tmp_path / "vector.db",
    )
    health = adapter.start(
        VectorStoreConfig(
            provider="kylin",
            collection_name="memory",
            expected_dimension=4,
            metric="cosine",
        )
    )
    adapter.ensure_collection(
        CollectionSpec(name="memory", dimension=4, metric="cosine")
    )
    result = adapter.upsert(
        [
            _vector_item(1, scene="desktop"),
            _vector_item(2, user_id="user-2"),
            _vector_item(3, scene="terminal"),
            _vector_item(4, status=MemoryStatus.TOMBSTONED),
        ]
    )

    hits = adapter.query(
        VectorQuery(
            user_id="user-1",
            status=MemoryStatus.ACTIVE,
            vector=[0.1, 0.2, 0.3, 0.4],
            top_k=10,
            timeout_ms=100,
            filters={"scene": "desktop"},
        )
    )
    deleted = adapter.delete([1, 99])

    assert health.status == "ok"
    assert result.upserted == 4
    assert [hit.vector_pk for hit in hits] == [1]
    assert deleted.deleted == 1
    assert deleted.missing_vector_pks == [99]
    assert native.opened and native.opened["encrypt"] is False
    adapter.close()
    assert native.closed is True


def test_vector_adapter_rejects_wrong_dimension(tmp_path) -> None:
    adapter = KylinVectorStoreAdapter(
        native=FakeVectorNative(),
        db_file=tmp_path / "vector.db",
    )
    adapter.start(
        VectorStoreConfig(
            provider="kylin",
            collection_name="memory",
            expected_dimension=4,
        )
    )

    wrong = _vector_item(1).model_copy(update={"vector": [0.1, 0.2]})
    with pytest.raises(Exception, match="dimension 2"):
        adapter.upsert([wrong])
