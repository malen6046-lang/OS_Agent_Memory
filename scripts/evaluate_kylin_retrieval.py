"""Evaluate real Kylin embedding/vector retrieval on Dataset V0.1."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adapters.embedding.kylin_provider import KylinEmbeddingProvider
from adapters.vector_store.kylin_vector_store import KylinVectorStoreAdapter
from contracts.schemas.common import MemoryStatus
from contracts.schemas.provider import (
    VectorHit,
    VectorItem,
    VectorQuery,
    VectorStoreConfig,
)
from evaluation.loaders import load_cases, load_corpus
from evaluation.metrics import hit_at_k, mrr, recall_at_k, stable_int_id
from modules.knowledge_retrieval.algorithm_v1_1.bm25 import BM25Retriever


SHARED_USER_ID = "usr_corpus_shared"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default="ensemble-embd_gte-base_uint8-text",
    )
    parser.add_argument("--expect-dim", type=int, default=768)
    parser.add_argument(
        "--split",
        choices=("dev", "held_out", "all"),
        default="dev",
    )
    parser.add_argument("--candidate-k", type=int, default=30)
    parser.add_argument("--query-timeout-ms", type=int, default=2000)
    parser.add_argument(
        "--db",
        type=Path,
        default=Path.home()
        / ".local/share/os-agent-memory/evaluation-vector.db",
    )
    parser.add_argument(
        "--collection",
        default="os_agent_memory_retrieval_evaluation",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    if args.expect_dim <= 0:
        parser.error("--expect-dim must be positive")
    if args.candidate_k < 10 or args.candidate_k > 100:
        parser.error("--candidate-k must be between 10 and 100")

    corpus = load_corpus()
    queries = load_cases("retrieval", split=args.split)
    if not corpus or not queries:
        raise RuntimeError("retrieval evaluation dataset is empty")

    embedding = KylinEmbeddingProvider(
        model_name=args.model,
        expected_dimension=args.expect_dim,
    )
    vector_store = KylinVectorStoreAdapter(db_file=args.db)
    bm25 = BM25Retriever()
    vector_pks: list[int] = []
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

        corpus_embedding_ms: list[float] = []
        items: list[VectorItem] = []
        documents: list[dict[str, Any]] = []
        id_to_user: dict[str, str] = {}
        normalized_status_counts: dict[str, int] = {}
        for row in corpus:
            memory_id = str(row["memory_id"])
            user_id = str(row["user_id"])
            text = str(row.get("content_text", ""))
            dataset_status = str(row.get("status", MemoryStatus.ACTIVE.value))
            memory_status = _normalize_dataset_status(dataset_status)
            if dataset_status != memory_status.value:
                mapping = f"{dataset_status}->{memory_status.value}"
                normalized_status_counts[mapping] = (
                    normalized_status_counts.get(mapping, 0) + 1
                )
            elapsed_ms, batch = _timed(lambda text=text: embedding.encode([text]))
            corpus_embedding_ms.append(elapsed_ms)
            vector_pk = stable_int_id(memory_id)
            vector_pks.append(vector_pk)
            id_to_user[memory_id] = user_id
            items.append(
                VectorItem(
                    vector_pk=vector_pk,
                    memory_id=memory_id,
                    user_id=user_id,
                    status=memory_status,
                    vector=batch.vectors[0],
                    metadata={
                        "memory_kind": str(row.get("memory_kind", "semantic")),
                        "subtype": str(row.get("subtype", "fact")),
                    },
                )
            )
            documents.append(
                {
                    "doc_id": memory_id,
                    "memory_id": memory_id,
                    "text": text,
                    "content_text": text,
                    "user_id": user_id,
                    "memory_kind": str(row.get("memory_kind", "semantic")),
                    "status": memory_status.value,
                }
            )

        bm25.index(documents)
        upsert_ms, upserted = _timed(lambda: vector_store.upsert(items))
        if upserted.upserted != len(items):
            raise RuntimeError(
                f"expected {len(items)} corpus upserts, got {upserted.upserted}"
            )

        dense_rankings: list[list[str]] = []
        hybrid_rankings: list[list[str]] = []
        query_embedding_ms: list[float] = []
        vector_query_ms: list[float] = []
        dense_total_ms: list[float] = []
        hybrid_total_ms: list[float] = []
        cross_user_dense = 0
        cross_user_hybrid = 0
        case_results: list[dict[str, Any]] = []

        for query_case in queries:
            query_text = str(query_case["query"])
            user_id = str(query_case["user_id"])
            dense_started = time.perf_counter()
            embed_ms, batch = _timed(
                lambda query_text=query_text: embedding.encode([query_text])
            )
            vector_ms, hits = _timed(
                lambda user_id=user_id, vector=batch.vectors[0]: _query_dense_scopes(
                    vector_store,
                    user_id=user_id,
                    vector=vector,
                    top_k=args.candidate_k,
                    timeout_ms=args.query_timeout_ms,
                )
            )
            dense_ids = [hit.memory_id for hit in hits]
            dense_elapsed_ms = (time.perf_counter() - dense_started) * 1000

            hybrid_started = time.perf_counter()
            sparse_ids = _search_sparse_scopes(
                bm25,
                query=query_text,
                user_id=user_id,
                top_k=args.candidate_k,
            )
            hybrid_ids = _rrf(dense_ids, sparse_ids, top_k=10)
            hybrid_elapsed_ms = dense_elapsed_ms + (
                time.perf_counter() - hybrid_started
            ) * 1000

            dense_rankings.append(dense_ids[:10])
            hybrid_rankings.append(hybrid_ids)
            query_embedding_ms.append(embed_ms)
            vector_query_ms.append(vector_ms)
            dense_total_ms.append(dense_elapsed_ms)
            hybrid_total_ms.append(hybrid_elapsed_ms)
            if _has_cross_user(dense_ids[:10], user_id, id_to_user):
                cross_user_dense += 1
            if _has_cross_user(hybrid_ids, user_id, id_to_user):
                cross_user_hybrid += 1
            gold_ids = [
                str(value)
                for value in query_case.get("expected", {}).get(
                    "gold_memory_ids", []
                )
            ]
            dense_scores = [
                {
                    "memory_id": hit.memory_id,
                    "user_id": hit.user_id,
                    "score": round(hit.score, 6),
                }
                for hit in hits[:10]
            ]
            case_results.append(
                {
                    "case_id": str(query_case.get("case_id", "")),
                    "user_id": user_id,
                    "query": query_text,
                    "tags": [str(value) for value in query_case.get("tags", [])],
                    "gold_memory_ids": gold_ids,
                    "dense_top_10": dense_ids[:10],
                    "dense_top_10_scores": dense_scores,
                    "dense_top1_score": (
                        dense_scores[0]["score"] if dense_scores else None
                    ),
                    "dense_top2_score": (
                        dense_scores[1]["score"]
                        if len(dense_scores) > 1
                        else None
                    ),
                    "dense_top1_margin": (
                        round(
                            float(dense_scores[0]["score"])
                            - float(dense_scores[1]["score"]),
                            6,
                        )
                        if len(dense_scores) > 1
                        else None
                    ),
                    "dense_first_relevant_score": _first_relevant_score(
                        hits[:10], gold_ids
                    ),
                    "hybrid_top_10": hybrid_ids,
                    "dense_first_relevant_rank": _first_relevant_rank(
                        dense_ids[:10], gold_ids
                    ),
                    "hybrid_first_relevant_rank": _first_relevant_rank(
                        hybrid_ids, gold_ids
                    ),
                    "dense_total_ms": round(dense_elapsed_ms, 3),
                    "hybrid_total_ms": round(hybrid_elapsed_ms, 3),
                }
            )

        gold_rankings = [
            [str(value) for value in case.get("expected", {}).get("gold_memory_ids", [])]
            for case in queries
        ]
        report = {
            "status": "ok",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "dataset": {
                "version": "0.1.0",
                "split": args.split,
                "corpus_size": len(corpus),
                "query_count": len(queries),
                "answerable_query_count": sum(bool(gold) for gold in gold_rankings),
                "no_answer_query_count": sum(not gold for gold in gold_rankings),
                "status_normalizations": normalized_status_counts,
            },
            "model": args.model,
            "dimension": args.expect_dim,
            "metric": "cosine",
            "candidate_k": args.candidate_k,
            "db_file": str(args.db.expanduser().resolve()),
            "collection": args.collection,
            "startup_ms": {
                "embedding": round(embedding_start_ms, 3),
                "vector_store": round(vector_start_ms, 3),
            },
            "corpus_indexing": {
                "embedding_ms": _summary(corpus_embedding_ms),
                "upsert_total_ms": round(upsert_ms, 3),
                "upsert_count": upserted.upserted,
            },
            "dense": {
                **_metrics(dense_rankings, gold_rankings),
                "cross_user_leak_cases": cross_user_dense,
                "score_diagnostics": _score_diagnostics(case_results),
                "latency_ms": {
                    "embedding": _summary(query_embedding_ms),
                    "vector_query": _summary(vector_query_ms),
                    "total": _summary(dense_total_ms),
                },
            },
            "hybrid_rrf": {
                **_metrics(hybrid_rankings, gold_rankings),
                "cross_user_leak_cases": cross_user_hybrid,
                "latency_ms": {
                    "total": _summary(hybrid_total_ms),
                },
            },
            "case_results": case_results,
            "embedding_health": embedding_health.model_dump(mode="json"),
            "vector_store_health": vector_health.model_dump(mode="json"),
            "total_elapsed_ms": round(
                (time.perf_counter() - started_at) * 1000,
                3,
            ),
            "cleanup": "pending",
        }

        delete_ms, deleted = _timed(lambda: vector_store.delete(vector_pks))
        if deleted.deleted != len(vector_pks):
            raise RuntimeError(
                f"evaluation cleanup deleted {deleted.deleted}/{len(vector_pks)}; "
                f"missing={deleted.missing_vector_pks}"
            )
        report["cleanup"] = "passed"
        report["cleanup_ms"] = round(delete_ms, 3)
        vector_pks.clear()

        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        print(rendered)
        if args.output is not None:
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(rendered + "\n", encoding="utf-8")
            print(f"report written: {output}", file=sys.stderr)
        return 0
    finally:
        if vector_pks:
            try:
                vector_store.delete(vector_pks)
            except Exception:
                pass
        vector_store.close()
        embedding.close()


def _metrics(
    rankings: list[list[str]],
    gold_rankings: list[list[str]],
) -> dict[str, Any]:
    ks = (1, 3, 5, 10)
    answerable = [
        (ranked, gold)
        for ranked, gold in zip(rankings, gold_rankings)
        if gold
    ]
    no_answer = [
        ranked
        for ranked, gold in zip(rankings, gold_rankings)
        if not gold
    ]
    count = max(len(answerable), 1)
    return {
        "recall_at_k": {
            str(k): round(
                sum(recall_at_k(ranked, gold, k) for ranked, gold in answerable)
                / count,
                6,
            )
            for k in ks
        },
        "hit_at_k": {
            str(k): round(
                sum(hit_at_k(ranked, gold, k) for ranked, gold in answerable)
                / count,
                6,
            )
            for k in ks
        },
        "mrr": round(
            sum(mrr(ranked, gold) for ranked, gold in answerable)
            / count,
            6,
        ),
        "answerable_query_count": len(answerable),
        "no_answer": {
            "query_count": len(no_answer),
            "correct_empty_count": sum(not ranked for ranked in no_answer),
            "accuracy": round(
                sum(not ranked for ranked in no_answer) / max(len(no_answer), 1),
                6,
            ),
        },
    }


def _query_dense_scopes(
    vector_store: KylinVectorStoreAdapter,
    *,
    user_id: str,
    vector: list[float],
    top_k: int,
    timeout_ms: int,
) -> list[VectorHit]:
    """Search the private scope plus the shared corpus, then merge by score."""
    hits: list[VectorHit] = []
    for scope_user_id in dict.fromkeys((user_id, SHARED_USER_ID)):
        hits.extend(
            vector_store.query(
                VectorQuery(
                    user_id=scope_user_id,
                    status=MemoryStatus.ACTIVE,
                    vector=vector,
                    top_k=top_k,
                    timeout_ms=timeout_ms,
                )
            )
        )
    best_by_memory: dict[str, VectorHit] = {}
    for hit in hits:
        previous = best_by_memory.get(hit.memory_id)
        if previous is None or hit.score > previous.score:
            best_by_memory[hit.memory_id] = hit
    return sorted(
        best_by_memory.values(),
        key=lambda hit: (-hit.score, hit.memory_id),
    )[:top_k]


def _search_sparse_scopes(
    bm25: BM25Retriever,
    *,
    query: str,
    user_id: str,
    top_k: int,
) -> list[str]:
    """Search BM25 across the same visibility scopes as dense retrieval."""
    scored: list[tuple[str, float]] = []
    for scope_user_id in dict.fromkeys((user_id, SHARED_USER_ID)):
        for item in bm25.search(
            query,
            top_k=top_k,
            filter_user_id=scope_user_id,
            filter_status=MemoryStatus.ACTIVE.value,
        ):
            scored.append((str(item["doc_id"]), float(item["score"])))
    best_by_memory: dict[str, float] = {}
    for memory_id, score in scored:
        best_by_memory[memory_id] = max(score, best_by_memory.get(memory_id, score))
    return [
        memory_id
        for memory_id, _ in sorted(
            best_by_memory.items(),
            key=lambda item: (-item[1], item[0]),
        )[:top_k]
    ]


def _first_relevant_rank(ranked: list[str], gold: list[str]) -> int | None:
    gold_set = set(gold)
    for rank, memory_id in enumerate(ranked, 1):
        if memory_id in gold_set:
            return rank
    return None


def _first_relevant_score(
    hits: list[VectorHit],
    gold: list[str],
) -> float | None:
    gold_set = set(gold)
    for hit in hits:
        if hit.memory_id in gold_set:
            return round(hit.score, 6)
    return None


def _score_diagnostics(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    answerable_top1 = [
        float(case["dense_top1_score"])
        for case in case_results
        if case["gold_memory_ids"] and case["dense_top1_score"] is not None
    ]
    no_answer_top1 = [
        float(case["dense_top1_score"])
        for case in case_results
        if not case["gold_memory_ids"] and case["dense_top1_score"] is not None
    ]
    relevant_scores = [
        float(case["dense_first_relevant_score"])
        for case in case_results
        if case["dense_first_relevant_score"] is not None
    ]
    margins = [
        float(case["dense_top1_margin"])
        for case in case_results
        if case["dense_top1_margin"] is not None
    ]
    return {
        "answerable_top1": (
            _summary(answerable_top1) if answerable_top1 else None
        ),
        "no_answer_top1": (
            _summary(no_answer_top1) if no_answer_top1 else None
        ),
        "first_relevant": (
            _summary(relevant_scores) if relevant_scores else None
        ),
        "top1_margin": _summary(margins) if margins else None,
        "note": (
            "Dataset V0.1 dev has only one no-answer query; do not choose a "
            "production rejection threshold from this sample alone."
        ),
    }


def _normalize_dataset_status(value: str) -> MemoryStatus:
    """Map Dataset V0.1's legacy ``inactive`` label to the frozen enum."""
    if value == "inactive":
        return MemoryStatus.EXPIRED
    try:
        return MemoryStatus(value)
    except ValueError as exc:
        raise ValueError(f"unsupported corpus memory status: {value!r}") from exc


def _rrf(
    dense_ids: list[str],
    sparse_ids: list[str],
    *,
    top_k: int,
    rank_constant: int = 60,
) -> list[str]:
    scores: dict[str, float] = {}
    order: dict[str, int] = {}
    for source in (dense_ids, sparse_ids):
        for rank, memory_id in enumerate(source, 1):
            order.setdefault(memory_id, len(order))
            scores[memory_id] = scores.get(memory_id, 0.0) + 1.0 / (
                rank_constant + rank
            )
    ranked = sorted(scores, key=lambda memory_id: (-scores[memory_id], order[memory_id]))
    return ranked[:top_k]


def _has_cross_user(
    memory_ids: list[str],
    user_id: str,
    id_to_user: dict[str, str],
) -> bool:
    return any(
        id_to_user.get(memory_id) not in {None, user_id, "usr_corpus_shared"}
        for memory_id in memory_ids
    )


def _timed(operation: Any) -> tuple[float, Any]:
    started = time.perf_counter()
    result = operation()
    return (time.perf_counter() - started) * 1000, result


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        raise ValueError("sample cannot be empty")
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


if __name__ == "__main__":
    raise SystemExit(main())
