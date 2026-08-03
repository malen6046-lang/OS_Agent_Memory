# -*- coding: utf-8 -*-
"""Retrieval eval — data from knowledge_corpus.jsonl + retrieval_queries.jsonl."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from pprint import pprint
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from adapters.vector_store.memory_vector_store import MemoryVectorStore
from evaluation.loaders import load_cases, load_corpus
from evaluation.metrics import hit_at_k, mrr, percentile, recall_at_k, stable_embed, stable_int_id
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever


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


def run_retrieval_eval(*, split: str = "dev") -> dict[str, Any]:
    corpus = load_corpus()
    queries = load_cases("retrieval", split=split)
    hr = build_retriever(corpus)
    ks = [1, 3, 5, 10]
    recalls = {k: [] for k in ks}
    hits = {k: [] for k in ks}
    mrrs, lats = [], []
    cross_user_leak = 0
    for q in queries:
        uid = q.get("user_id")
        resp = hr.search({"query": q["query"], "user_id": uid, "top_k": 10})
        ranked = [r["memory_id"] for r in resp.get("results", [])]
        gold = q.get("expected", {}).get("gold_memory_ids", [])
        for k in ks:
            recalls[k].append(recall_at_k(ranked, gold, k))
            hits[k].append(hit_at_k(ranked, gold, k))
        mrrs.append(mrr(ranked, gold))
        lats.append(float(resp.get("meta", {}).get("elapsed_ms", 0.0)))
        # user isolation check against corpus metadata
        id2user = {m["memory_id"]: m.get("user_id") for m in corpus}
        for mid in ranked:
            if uid and id2user.get(mid) not in (None, uid):
                cross_user_leak += 1
                break
    n = max(len(queries), 1)
    return {
        "task": "retrieval",
        "split": split,
        "n": len(queries),
        "corpus_size": len(corpus),
        "recall_at_k": {str(k): sum(recalls[k]) / n for k in ks},
        "hit_at_k": {str(k): sum(hits[k]) / n for k in ks},
        "mrr": sum(mrrs) / n,
        "latency_ms": {
            "p50": percentile(lats, 50),
            "p95": percentile(lats, 95),
            "mean": sum(lats) / n,
        },
        "cross_user_leak_cases": cross_user_leak,
        "id_hash": "sha256",
        "backend": "HybridRetriever+BM25+MemoryVectorStore+DemoEmbedding(sha256)",
        "note": "DemoEmbedding latency is NOT Kylin ≤500ms evidence",
        "status": "baseline_not_competition_claim",
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    args = p.parse_args()
    pprint(run_retrieval_eval(split=args.split))


if __name__ == "__main__":
    main()
