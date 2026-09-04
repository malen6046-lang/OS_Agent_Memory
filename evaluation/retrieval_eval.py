# -*- coding: utf-8 -*-
"""Retrieval eval — data from knowledge_corpus.jsonl + retrieval_queries.jsonl."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from pprint import pprint
from typing import Any, Callable

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from adapters.vector_store.memory_vector_store import MemoryVectorStore
from evaluation.loaders import load_cases, load_corpus
from evaluation.metrics import hit_at_k, mrr, percentile, recall_at_k, stable_embed, stable_int_id
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever

# search_fn(query_case) -> {"results": [{"memory_id": ...}, ...], "meta": {"elapsed_ms": float}}
SearchFn = Callable[[dict[str, Any]], dict[str, Any]]


class _DemoEmbedding:
    def __init__(self, dim: int = 32):
        self._dim = dim

    def health(self, deep: bool = False) -> dict:
        return {"provider": "demo", "status": "healthy", "dimension": self._dim}

    def encode(self, texts: list[str]) -> dict:
        return {
            "vectors": [stable_embed(t, self._dim) for t in texts],
            "dimension": self._dim,
            "model_name": "demo-sha256",
            "errors": None,
        }


def build_retriever(corpus: list[dict[str, Any]] | None = None, dim: int = 32) -> HybridRetriever:
    rows = corpus if corpus is not None else load_corpus()
    docs = []
    for m in rows:
        mid = m["memory_id"]
        docs.append({
            "doc_id": mid,
            "text": m.get("content_text", ""),
            "content_text": m.get("content_text", ""),
            "user_id": m.get("user_id", ""),
            "memory_kind": m.get("memory_kind", "semantic"),
            "status": m.get("status", "active"),
            "memory_id": mid,
        })
    emb = _DemoEmbedding(dim=dim)
    vs = MemoryVectorStore(dim=dim)
    bm25 = BM25Retriever()
    bm25.index(docs)
    vs.upsert([{
        "vector_pk": stable_int_id(d["memory_id"]),
        "vector": stable_embed(d["content_text"], dim),
        "memory_id": d["memory_id"],
        "user_id": d["user_id"],
        "memory_kind": d["memory_kind"],
        "status": d["status"],
        "content_text": d["content_text"],
    } for d in docs])
    return HybridRetriever(emb, vs, bm25)


def _topic_of(memory_id: str, corpus_by_id: dict[str, dict[str, Any]]) -> str | None:
    row = corpus_by_id.get(memory_id) or {}
    return row.get("canonical_topic_id") or (row.get("attributes") or {}).get("canonical_topic_id")


def _no_answer_correct(ranked: list[str], resp: dict[str, Any]) -> bool:
    """Refusal check for retrieval-only eval.

    Correct when the backend returns no hits, or explicitly marks refusal.
    Score thresholds are only used when ``meta.no_answer_score_threshold`` is set
    by an injected search_fn (avoid false PASS on uncalibrated demo scores).
    """
    meta = resp.get("meta") or {}
    if meta.get("refused") or meta.get("no_answer") or meta.get("is_no_answer"):
        return True
    if not ranked:
        return True
    threshold = meta.get("no_answer_score_threshold")
    if threshold is None:
        return False
    results = resp.get("results") or []
    scores: list[float] = []
    for r in results[:5]:
        for key in ("score", "hybrid_score", "similarity"):
            if isinstance(r.get(key), (int, float)):
                scores.append(float(r[key]))
                break
    if not scores:
        return False
    return max(scores) < float(threshold)


def run_retrieval_eval(
    *,
    split: str = "dev",
    search_fn: SearchFn | None = None,
) -> dict[str, Any]:
    """Offline retrieval eval. Inject real KnowledgeService via ``search_fn``.

    Formal Recall@K / MRR are computed on **answerable** queries only
    (non-empty ``gold_memory_ids``). Empty-gold queries contribute to
    ``no_answer_accuracy`` instead — ``recall_at_k()`` math is unchanged.
    """
    corpus = load_corpus()
    corpus_by_id = {m["memory_id"]: m for m in corpus}
    queries = load_cases("retrieval", split=split)
    hr = None if search_fn is not None else build_retriever(corpus)
    ks = [1, 3, 5, 10]
    recalls = {k: [] for k in ks}
    hits = {k: [] for k in ks}
    topic_recalls = {k: [] for k in ks}
    mrrs, lats = [], []
    no_answer_hits: list[float] = []
    cross_user_leak = 0
    answerable_n = 0
    no_answer_n = 0

    for q in queries:
        uid = q.get("user_id")
        if search_fn is not None:
            resp = search_fn(q)
        else:
            assert hr is not None
            resp = hr.search({"query": q["query"], "user_id": uid, "top_k": 10})
        ranked = [r["memory_id"] for r in resp.get("results", [])]
        expected = q.get("expected") or {}
        gold = list(expected.get("gold_memory_ids") or [])
        gold_topics = list(expected.get("gold_topic_ids") or [])
        if not gold_topics and gold:
            for g in gold:
                tid = _topic_of(g, corpus_by_id)
                if tid and tid not in gold_topics:
                    gold_topics.append(tid)
        lats.append(float(resp.get("meta", {}).get("elapsed_ms", 0.0)))

        # user isolation check against corpus metadata
        id2user = {m["memory_id"]: m.get("user_id") for m in corpus}
        for mid in ranked:
            owner = id2user.get(mid)
            if uid and owner not in (None, uid, "usr_corpus_shared"):
                cross_user_leak += 1
                break

        is_no_answer = bool(expected.get("is_no_answer")) or (len(gold) == 0)
        if is_no_answer:
            no_answer_n += 1
            no_answer_hits.append(1.0 if _no_answer_correct(ranked, resp) else 0.0)
            continue

        answerable_n += 1
        for k in ks:
            recalls[k].append(recall_at_k(ranked, gold, k))
            hits[k].append(hit_at_k(ranked, gold, k))
            if gold_topics:
                ranked_topics = []
                for mid in ranked[:k]:
                    tid = _topic_of(mid, corpus_by_id)
                    if tid:
                        ranked_topics.append(tid)
                topic_recalls[k].append(recall_at_k(ranked_topics, gold_topics, k))
        mrrs.append(mrr(ranked, gold))

    denom = max(answerable_n, 1)
    backend = (
        "injected_search_fn"
        if search_fn is not None
        else "HybridRetriever+BM25+MemoryVectorStore+DemoEmbedding(sha256)"
    )
    return {
        "task": "retrieval",
        "split": split,
        "n": len(queries),
        "answerable_n": answerable_n,
        "no_answer_n": no_answer_n,
        "corpus_size": len(corpus),
        # Primary (answerable only) — keeps freeze-compatible key names
        "recall_at_k": {str(k): (sum(recalls[k]) / denom if answerable_n else 0.0) for k in ks},
        "hit_at_k": {str(k): (sum(hits[k]) / denom if answerable_n else 0.0) for k in ks},
        "mrr": (sum(mrrs) / denom) if answerable_n else 0.0,
        "canonical_topic_recall_at_k": {
            str(k): (sum(topic_recalls[k]) / len(topic_recalls[k]) if topic_recalls[k] else 0.0)
            for k in ks
        },
        "no_answer_accuracy": (
            sum(no_answer_hits) / len(no_answer_hits) if no_answer_hits else None
        ),
        "latency_ms": {
            "p50": percentile(lats, 50),
            "p95": percentile(lats, 95),
            "mean": sum(lats) / max(len(lats), 1),
        },
        "cross_user_leak_cases": cross_user_leak,
        "id_hash": "sha256",
        "backend": backend,
        "note": (
            "Recall/MRR on answerable only; no_answer_accuracy separate. "
            "DemoEmbedding latency is NOT Kylin ≤500ms evidence"
        ),
        "status": "baseline_not_competition_claim",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "validation", "final_test", "held_out", "all"])
    args = p.parse_args()
    pprint(run_retrieval_eval(split=args.split))


if __name__ == "__main__":
    main()
