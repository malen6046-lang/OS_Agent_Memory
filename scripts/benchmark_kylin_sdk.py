"""Real-machine latency benchmark for the Kylin SDK adapters.

The benchmark keeps generated vectors in a dedicated collection/database and
deletes every generated item before exit. It prints aggregate statistics only;
embedding vectors never appear in the report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

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
        "--model",
        default="ensemble-embd_gte-base_uint8-text",
    )
    parser.add_argument("--expect-dim", type=int, default=768)
    parser.add_argument("--iterations", type=int, default=30)
    parser.add_argument("--warmup-iterations", type=int, default=3)
    parser.add_argument("--query-timeout-ms", type=int, default=2000)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path.home()
        / ".local/share/os-agent-memory/benchmark-vector.db",
    )
    parser.add_argument(
        "--collection",
        default="os_agent_memory_sdk_benchmark",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.iterations < 5:
        parser.error("--iterations must be at least 5")
    if args.warmup_iterations < 0:
        parser.error("--warmup-iterations cannot be negative")
    if args.expect_dim <= 0:
        parser.error("--expect-dim must be positive")

    run_id = uuid4().hex
    user_id = f"sdk-benchmark-{run_id}"
    embedding = KylinEmbeddingProvider(
        model_name=args.model,
        expected_dimension=args.expect_dim,
    )
    vector_store = KylinVectorStoreAdapter(db_file=args.db)
    vector_pks: list[int] = []
    measurements: dict[str, list[float]] = {
        "embedding_ms": [],
        "upsert_ms": [],
        "query_ms": [],
        "encode_upsert_query_ms": [],
        "delete_ms": [],
    }
    started_at = time.perf_counter()

    try:
        embedding_start_ms, embedding_health = _timed(embedding.start)
        vector_start_ms, vector_health = _timed(
            lambda: vector_store.start(
                VectorStoreConfig(
                    provider="kylin",
                    collection_name=args.collection,
                    expected_dimension=args.expect_dim,
                    metric="cosine",
                )
            )
        )

        for index in range(args.warmup_iterations):
            embedding.encode([_text(index, warmup=True)])

        for index in range(args.iterations):
            text = _text(index, warmup=False)
            cycle_started = time.perf_counter()
            embedding_ms, batch = _timed(lambda: embedding.encode([text]))
            vector_pk = _vector_pk(run_id, index)
            memory_id = f"sdk-benchmark-memory-{run_id}-{index}"
            item = VectorItem(
                vector_pk=vector_pk,
                memory_id=memory_id,
                user_id=user_id,
                status=MemoryStatus.ACTIVE,
                vector=batch.vectors[0],
                metadata={"benchmark_run": run_id, "iteration": index},
            )
            upsert_ms, upserted = _timed(lambda: vector_store.upsert([item]))
            vector_pks.append(vector_pk)
            query_ms, hits = _timed(
                lambda: vector_store.query(
                    VectorQuery(
                        user_id=user_id,
                        status=MemoryStatus.ACTIVE,
                        vector=batch.vectors[0],
                        top_k=1,
                        timeout_ms=args.query_timeout_ms,
                    )
                )
            )
            cycle_ms = (time.perf_counter() - cycle_started) * 1000
            if upserted.upserted != 1:
                raise RuntimeError(
                    f"iteration {index}: expected one upsert, got "
                    f"{upserted.upserted}"
                )
            if not hits or hits[0].memory_id != memory_id:
                raise RuntimeError(
                    f"iteration {index}: exact vector query did not return "
                    f"{memory_id}"
                )
            measurements["embedding_ms"].append(embedding_ms)
            measurements["upsert_ms"].append(upsert_ms)
            measurements["query_ms"].append(query_ms)
            measurements["encode_upsert_query_ms"].append(cycle_ms)

        for vector_pk in vector_pks:
            delete_ms, deleted = _timed(
                lambda vector_pk=vector_pk: vector_store.delete([vector_pk])
            )
            if deleted.deleted != 1:
                raise RuntimeError(
                    f"vector cleanup failed for {vector_pk}: "
                    f"deleted={deleted.deleted}, "
                    f"missing={deleted.missing_vector_pks}"
                )
            measurements["delete_ms"].append(delete_ms)
        vector_pks.clear()

        report = {
            "status": "ok",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "platform": "kylin",
            "model": args.model,
            "dimension": args.expect_dim,
            "metric": "cosine",
            "iterations": args.iterations,
            "warmup_iterations": args.warmup_iterations,
            "db_file": str(args.db.expanduser().resolve()),
            "collection": args.collection,
            "startup_ms": {
                "embedding": round(embedding_start_ms, 3),
                "vector_store": round(vector_start_ms, 3),
            },
            "embedding_health": embedding_health.model_dump(mode="json"),
            "vector_store_health": vector_health.model_dump(mode="json"),
            "latency_ms": {
                name: _summary(values)
                for name, values in measurements.items()
            },
            "total_elapsed_ms": round(
                (time.perf_counter() - started_at) * 1000,
                3,
            ),
        }
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        if args.output is not None:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            print(f"report written: {output}", file=sys.stderr)
        return 0
    finally:
        for vector_pk in vector_pks:
            try:
                vector_store.delete([vector_pk])
            except Exception:
                pass
        vector_store.close()
        embedding.close()


def _timed(operation: Callable[[], Any]) -> tuple[float, Any]:
    started = time.perf_counter()
    result = operation()
    return (time.perf_counter() - started) * 1000, result


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("latency sample cannot be empty")
    ordered = sorted(values)
    return {
        "min": round(ordered[0], 3),
        "mean": round(statistics.fmean(ordered), 3),
        "p50": round(_percentile(ordered, 0.50), 3),
        "p95": round(_percentile(ordered, 0.95), 3),
        "p99": round(_percentile(ordered, 0.99), 3),
        "max": round(ordered[-1], 3),
    }


def _percentile(ordered: list[float], quantile: float) -> float:
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _vector_pk(run_id: str, index: int) -> int:
    digest = hashlib.blake2b(
        f"{run_id}\0{index}".encode("utf-8"),
        digest_size=8,
        person=b"osam-bench",
    ).digest()
    return int.from_bytes(digest, "big") & (2**63 - 1)


def _text(index: int, *, warmup: bool) -> str:
    phase = "预热" if warmup else "性能测试"
    return (
        f"麒麟 OS Agent 记忆向量{phase}样本 {index}："
        "用户偏好深色主题，并经常使用 Python 处理文档。"
    )


if __name__ == "__main__":
    raise SystemExit(main())
