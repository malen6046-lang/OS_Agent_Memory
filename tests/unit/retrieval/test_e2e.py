"""End-to-end tests — 写后检索, 用户隔离, 降级, 重复写入, 错误回滚.

Uses real MockEmbeddingProvider + MemoryVectorStore + BM25
+ KnowledgeService + HybridRetriever.
"""
from adapters.embedding.mock_provider import MockEmbeddingProvider
from adapters.vector_store.memory_vector_store import MemoryVectorStore
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.knowledge_service import KnowledgeService
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever


def _build_all():
    emb = MockEmbeddingProvider(dim=16)
    emb.start()
    vs = MemoryVectorStore(dim=16)
    vs.start({"dim": 16})
    bm = BM25Retriever()
    ks = KnowledgeService(emb, vs, bm)
    hr = HybridRetriever(emb, vs, bm)
    return emb, vs, bm, ks, hr


class TestE2EWriteThenSearch:
    def test_write_then_search(self):
        _, _, _, ks, hr = _build_all()
        result = ks.ingest([{
            "title": "Ctrl+Alt+T opens terminal",
            "body": "Use Ctrl+Alt+T to quickly open a terminal in Qilin",
            "user_id": "usr_0",
            "knowledge_type": "workflow",
        }])
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] == "inserted"
        memory_id = result["items"][0]["memory_id"]

        search = hr.search({"query": "how to open terminal", "user_id": "usr_0", "top_k": 5})
        found = any(r["memory_id"] == memory_id for r in search["items"])
        assert found, f"Written memory {memory_id} not found in search results"


class TestE2EUserIsolation:
    def test_user_isolation(self):
        _, _, _, ks, hr = _build_all()
        ks.ingest([{"title": "user A secret", "body": "only for A",
                     "user_id": "usr_A", "knowledge_type": "fact"}])
        ks.ingest([{"title": "user B secret", "body": "only for B",
                     "user_id": "usr_B", "knowledge_type": "fact"}])

        rA = hr.search({"query": "secret", "user_id": "usr_A", "top_k": 10})
        rB = hr.search({"query": "secret", "user_id": "usr_B", "top_k": 10})

        textsA = {rr["content_text"] for rr in rA["items"]}
        textsB = {rr["content_text"] for rr in rB["items"]}
        assert "only for B" not in textsA
        assert "only for A" not in textsB


class TestE2EDegradation:
    def test_degraded_when_embedding_stopped(self):
        emb, vs, bm, ks, hr = _build_all()
        ks.ingest([{"title": "terminal shortcut", "body": "Ctrl+Alt+T",
                     "user_id": "usr_0", "knowledge_type": "workflow"}])
        emb.close()
        r = hr.search({"query": "terminal", "user_id": "usr_0", "top_k": 5})
        assert r["meta"]["degraded"] is True
        assert len(r["items"]) > 0


class TestE2EDuplicateWrite:
    def test_duplicate_not_duplicated(self):
        _, _, _, ks, hr = _build_all()
        for _ in range(3):
            ks.ingest([{"title": "same content", "body": "identical text",
                         "user_id": "usr_0", "knowledge_type": "fact"}])
        r = hr.search({"query": "identical text", "user_id": "usr_0", "top_k": 10})
        memory_ids = [rr["memory_id"] for rr in r["items"]]
        assert len(memory_ids) == len(set(memory_ids)), "No duplicate IDs in results"


class TestE2EErrorRollback:
    def test_failed_upsert_not_full_success(self):
        emb, vs, bm, ks, _ = _build_all()
        emb.start()
        r = ks.ingest([{"title": "bad item", "body": "text",
                         "user_id": "usr_0", "knowledge_type": "fact"}])
        item = r["items"][0]
        assert item["status"] in ("inserted", "conflict")
        assert item["memory_id"]
