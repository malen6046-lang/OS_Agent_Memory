"""Real-machine smoke test for the two Kylin SDK adapters."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

# Allow this source-tree smoke test to run before the full project (and its
# database dependencies) has been installed into the active virtualenv.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.embedding.kylin_provider import KylinEmbeddingProvider
from adapters.vector_store.kylin_vector_store import KylinVectorStoreAdapter
from contracts.schemas.common import MemoryStatus
from contracts.schemas.provider import VectorItem, VectorQuery, VectorStoreConfig


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", default="ensemble-embd_gte-base_uint8-text"
    )
    parser.add_argument("--expect-dim", type=int, default=768)
    parser.add_argument("--db", type=Path, default=Path("data/vector.db"))
    parser.add_argument("--collection", default="os_agent_memory_sdk_smoke")
    parser.add_argument("--text", default="麒麟操作系统 OS Agent 记忆检索测试")
    args = parser.parse_args()

    embedding = KylinEmbeddingProvider(
        model_name=args.model,
        expected_dimension=args.expect_dim,
    )
    vector_store = KylinVectorStoreAdapter(db_file=args.db)
    started_at = time.perf_counter()
    try:
        embedding_health = embedding.start()
        batch = embedding.encode([args.text])
        vector_health = vector_store.start(
            VectorStoreConfig(
                provider="kylin",
                collection_name=args.collection,
                expected_dimension=batch.dimension,
                metric="cosine",
            )
        )
        vector_store.upsert(
            [
                VectorItem(
                    vector_pk=9_223_372_036_854_000_001,
                    memory_id="sdk-smoke-memory",
                    user_id="sdk-smoke-user",
                    status=MemoryStatus.ACTIVE,
                    vector=batch.vectors[0],
                    metadata={"smoke": True},
                )
            ]
        )
        hits = vector_store.query(
            VectorQuery(
                user_id="sdk-smoke-user",
                status=MemoryStatus.ACTIVE,
                vector=batch.vectors[0],
                top_k=1,
                timeout_ms=500,
                filters={"smoke": True},
            )
        )
        ok = bool(hits and hits[0].memory_id == "sdk-smoke-memory")
        print(
            json.dumps(
                {
                    "status": "ok" if ok else "failed",
                    "embedding": embedding_health.model_dump(mode="json"),
                    "vector_store": vector_health.model_dump(mode="json"),
                    "dimension": batch.dimension,
                    "hit_count": len(hits),
                    "latency_ms": round(
                        (time.perf_counter() - started_at) * 1000, 3
                    ),
                },
                ensure_ascii=False,
            )
        )
        return 0 if ok else 1
    finally:
        vector_store.close()
        embedding.close()


if __name__ == "__main__":
    raise SystemExit(main())
