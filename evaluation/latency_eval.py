"""延迟评测 — P50/P95/P99 检索延迟.

Usage:
    python -m evaluation.latency_eval
"""
import json
import time
import statistics
from adapters.embedding.mock_provider import MockEmbeddingProvider
from adapters.vector_store.memory_vector_store import MemoryVectorStore
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever


def evaluate_latency(n_queries: int = 100, batch_size: int = 50) -> dict:
    emb = MockEmbeddingProvider(dim=16)
    emb.start()
    vs = MemoryVectorStore(dim=16)
    vs.start({"dim": 16})
    bm = BM25Retriever()
    hr = HybridRetriever(emb, vs, bm)

    # 建立索引
    import hashlib
    docs = [{"doc_id": f"d{i}", "text": f"\u7cfb\u7edf\u8bb0\u5fc6\u6761\u76ee{i}\u9e92\u9e9f\u7ec8\u7aef\u6570\u636e\u5e93",
             "user_id": "u1", "status": "active"} for i in range(batch_size)]
    bm.index(docs)
    for d in docs:
        vec = emb.encode([d["text"]])["vectors"][0]
        pk = int(hashlib.md5(d["doc_id"].encode()).hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF
        vs.upsert([{"vector_pk": pk, "vector": vec, "memory_id": d["doc_id"], "user_id": "u1",
                    "memory_kind": "semantic", "status": "active", "scene": "office", "content_text": d["text"]}])

    latencies = []
    for i in range(n_queries):
        query = f"\u67e5\u8be2\u7ec8\u7aef\u6570\u636e\u5e93{i % batch_size}"
        t0 = time.time()
        hr.search({"query": query, "user_id": "u1", "top_k": 5})
        latencies.append((time.time() - t0) * 1000)

    latencies.sort()
    def percentile(p):
        idx = max(0, min(len(latencies) - 1, int(len(latencies) * p)))
        return round(latencies[idx], 2)

    return {
        "dataset": {"indexed": batch_size, "queries": n_queries},
        "p50_ms": percentile(0.50),
        "p95_ms": percentile(0.95),
        "p99_ms": percentile(0.99),
        "max_ms": round(max(latencies), 2),
        "avg_ms": round(sum(latencies) / len(latencies), 2),
        "within_500ms": "yes" if percentile(0.95) < 500 else "no",
    }


def main():
    print(json.dumps(evaluate_latency(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
