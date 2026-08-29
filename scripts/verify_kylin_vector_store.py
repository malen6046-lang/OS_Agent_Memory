"""End-to-end verification of Kylin Embedding and Vector Store adapters."""

from __future__ import annotations

import json
import time

from adapters.embedding.kylin_provider import KylinEmbeddingProvider
from adapters.vector_store.kylin_vector_store import KylinVectorStoreAdapter
from contracts.schemas.common import MemoryStatus
from contracts.schemas.provider import (
    CollectionSpec,
    VectorItem,
    VectorQuery,
    VectorStoreConfig,
)


MODEL = "ensemble-embd_gte-base_uint8-text"
COLLECTION = "os_agent_memory"
DIMENSION = 768


def main() -> int:
    embedding = KylinEmbeddingProvider(model_name=MODEL)
    vector_store = KylinVectorStoreAdapter()
    base_pk = time.time_ns() % (2**63 - 100)
    pks = [base_pk, base_pk + 1]
    summary: dict[str, object] = {}
    embedding_started = False
    vector_started = False
    try:
        embedding_health = embedding.start()
        embedding_started = True
        vector_health = vector_store.start(
            VectorStoreConfig(
                provider="kylin",
                collection_name=COLLECTION,
                expected_dimension=DIMENSION,
                metric="cosine",
            )
        )
        vector_started = True
        vector_store.ensure_collection(
            CollectionSpec(name=COLLECTION, dimension=DIMENSION, metric="cosine")
        )

        batch = embedding.encode(["用户喜欢深色主题。"])
        vector = batch.vectors[0]
        upsert = vector_store.upsert(
            [
                VectorItem(
                    vector_pk=pks[0],
                    memory_id=f"verify-{pks[0]}",
                    user_id="verify-user-a",
                    status=MemoryStatus.ACTIVE,
                    vector=vector,
                    metadata={"test_run": True},
                ),
                VectorItem(
                    vector_pk=pks[1],
                    memory_id=f"verify-{pks[1]}",
                    user_id="verify-user-b",
                    status=MemoryStatus.ACTIVE,
                    vector=vector,
                    metadata={"test_run": True},
                ),
            ]
        )
        hits = vector_store.query(
            VectorQuery(
                user_id="verify-user-a",
                status=MemoryStatus.ACTIVE,
                vector=vector,
                top_k=5,
                timeout_ms=500,
                filters={"test_run": True},
            )
        )
        if not hits or any(hit.user_id != "verify-user-a" for hit in hits):
            raise RuntimeError("user_id filter verification failed")
        if not any(hit.vector_pk == pks[0] for hit in hits):
            raise RuntimeError("newly upserted vector was not found")

        deleted = vector_store.delete(pks)
        summary = {
            "embedding_health": embedding_health.model_dump(mode="json"),
            "vector_health": vector_health.model_dump(mode="json"),
            "vector_dimension": len(vector),
            "upserted": upsert.upserted,
            "query_hit_count": len(hits),
            "query_hit_ids": [hit.vector_pk for hit in hits],
            "user_filter_verified": True,
            "deleted": deleted.deleted,
            "missing_vector_pks": deleted.missing_vector_pks,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    finally:
        if vector_started:
            try:
                vector_store.delete(pks)
            except Exception:
                pass
            vector_store.close()
        if embedding_started:
            embedding.close()


if __name__ == "__main__":
    raise SystemExit(main())
