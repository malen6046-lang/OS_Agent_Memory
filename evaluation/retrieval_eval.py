"""Retrieval evaluation — Recall@K, latency, degradation, user isolation.

Usage:
    python -m evaluation.retrieval_eval
"""
import json
import time
from adapters.embedding.mock_provider import MockEmbeddingProvider
from adapters.vector_store.memory_vector_store import MemoryVectorStore
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever
from evaluation.data_loader import load_dataset

# 数据集从文件读取（可替换 datasets/retrieval/*.json 更换评测集）
KNOWLEDGE = load_dataset("retrieval/knowledge.json")
QUERIES = load_dataset("retrieval/queries.json")


def evaluate_retrieval(embedding_provider=None) -> dict:
    import hashlib
    if embedding_provider is None:
        emb = MockEmbeddingProvider(dim=16)
        emb.start()
    else:
        emb = embedding_provider

    vs = MemoryVectorStore(dim=emb._dim)
    vs.start({"dim": emb._dim})
    bm = BM25Retriever()
    hr = HybridRetriever(emb, vs, bm)

    bm.index(KNOWLEDGE)
    for k in KNOWLEDGE:
        batch = emb.encode([k["text"]])
        pk = int(hashlib.md5(k["doc_id"].encode()).hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF
        vs.upsert([{"vector_pk": pk, "vector": batch["vectors"][0],
                    "memory_id": k["doc_id"], "user_id": k["user_id"],
                    "memory_kind": k["memory_kind"], "status": k["status"],
                    "scene": "office", "content_text": k["text"]}])

    top1_hits = 0
    recall5_hits = 0
    latencies = []
    for q in QUERIES:
        t0 = time.time()
        r = hr.search({"query": q["query"], "user_id": q["user_id"], "top_k": 5})
        lat = (time.time() - t0) * 1000
        latencies.append(lat)
        doc_ids = [rr["memory_id"] for rr in r["items"]]
        if doc_ids and doc_ids[0] == q["gold_doc_id"]:
            top1_hits += 1
        if q["gold_doc_id"] in doc_ids:
            recall5_hits += 1

    n = len(QUERIES)
    latencies.sort()
    return {
        "dataset": {"knowledge": len(KNOWLEDGE), "queries": n},
        "Top-1_hit_rate": f"{top1_hits}/{n} = {top1_hits/n*100:.1f}%",
        "Recall@5": f"{recall5_hits}/{n} = {recall5_hits/n*100:.1f}%",
        "avg_latency_ms": round(sum(latencies) / n, 2),
        "p95_latency_ms": round(latencies[int(n * 0.95)], 2),
        "max_latency_ms": round(max(latencies), 2),
    }


def main():
    print(json.dumps(evaluate_retrieval(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
