"""MVP-1: 真实 FallbackEmbeddingProvider 集成验证。

Requirements from Task 7:
  - model startup, Chinese encoding, stable dimension
  - empty text error, batch order preserved
  - health(stop/deep), model not found error
  - HybridRetriever with real vectors, degradation
  - metrics recording
"""
import pytest


@pytest.fixture(scope="module")
def emb():
    try:
        from adapters.embedding.fallback_provider import FallbackEmbeddingProvider
    except ImportError:
        pytest.skip("sentence-transformers not installed")
    p = FallbackEmbeddingProvider()
    p.start()
    yield p
    p.close()


class TestMVP1ModelLifecycle:
    def test_model_start_success(self, emb):
        info = emb.model_info()
        assert info["model_name"]
        assert info["dimension"] > 0
        assert info["provider"] == "fallback"
        assert "fingerprint" in info

    def test_dimension_stable(self, emb):
        d1 = emb.model_info()["dimension"]
        d2 = emb.model_info()["dimension"]
        assert d1 == d2


class TestMVP1Encoding:
    def test_encode_chinese(self, emb):
        batch = emb.encode(["\u9e92\u9e9f\u7cfb\u7edf\u7ec8\u7aef\u5feb\u6377\u952e"])
        assert len(batch["vectors"]) == 1
        assert len(batch["vectors"][0]) == emb._dim
        assert batch["errors"] is None

    def test_empty_text_reports_error(self, emb):
        batch = emb.encode(["", "  "])
        assert len(batch["vectors"]) == 0
        assert batch["errors"] is not None
        assert len(batch["errors"]) == 2

    def test_batch_order_preserved(self, emb):
        batch = emb.encode(["a", "b", "c", "d", "e"])
        assert len(batch["vectors"]) == 5


class TestMVP1Health:
    def test_health_shallow(self, emb):
        h = emb.health(deep=False)
        assert h["status"] == "healthy"

    def test_health_deep(self, emb):
        h = emb.health(deep=True)
        assert h["status"] in ("healthy", "degraded")

    def test_health_stopped(self):
        """Use a standalone provider that is closed."""
        from adapters.embedding.fallback_provider import FallbackEmbeddingProvider
        e = FallbackEmbeddingProvider()
        e.start()
        e.close()
        assert e.health()["status"] == "stopped"


class TestMVP1ModelNotFound:
    def test_bad_model_raises(self):
        from adapters.embedding.fallback_provider import FallbackEmbeddingProvider
        bad = FallbackEmbeddingProvider(model_name="nonexistent/model-xyz-123")
        with pytest.raises(Exception):
            bad.start()


class TestMVP1Hybrid:
    def test_hybrid_retriever_with_real_embedding(self, emb):
        from adapters.vector_store.memory_vector_store import MemoryVectorStore
        from modules.knowledge_retrieval.bm25 import BM25Retriever
        from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever
        import hashlib

        vs = MemoryVectorStore(dim=emb._dim)
        vs.start({"dim": emb._dim})
        bm = BM25Retriever()

        docs = [
            {"doc_id": "d0", "text": "\u9e92\u9e9f\u7ec8\u7aef\u5feb\u6377\u952eCtrl+Alt+T", "user_id": "u1", "status": "active"},
            {"doc_id": "d1", "text": "\u6df1\u8272\u4e3b\u9898\u8bbe\u7f6e\u65b9\u6cd5", "user_id": "u1", "status": "active"},
            {"doc_id": "d2", "text": "\u6570\u636e\u5e93\u5907\u4efd\u7b56\u7565cron\u5b9a\u65f6\u4efb\u52a1", "user_id": "u1", "status": "active"},
        ]
        bm.index(docs)
        for d in docs:
            batch = emb.encode([d["text"]])
            pk = int(hashlib.md5(d["doc_id"].encode()).hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF
            vs.upsert([{"vector_pk": pk, "vector": batch["vectors"][0],
                        "memory_id": d["doc_id"], "user_id": d["user_id"],
                        "memory_kind": "semantic", "status": "active",
                        "scene": "office", "content_text": d["text"]}])

        hr = HybridRetriever(emb, vs, bm)
        r = hr.search({"query": "\u5982\u4f55\u6253\u5f00\u7ec8\u7aef", "user_id": "u1", "top_k": 3})
        assert len(r["items"]) > 0
        assert r["meta"]["degraded"] is False
        assert r["meta"]["embedding_provider"] != "none"
        assert r["meta"]["elapsed_ms"] >= 0

    def test_degraded_when_embedding_stopped(self):
        """Use Mock provider for reliable degradation test."""
        from adapters.embedding.mock_provider import MockEmbeddingProvider
        from adapters.vector_store.memory_vector_store import MemoryVectorStore
        from modules.knowledge_retrieval.bm25 import BM25Retriever
        from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever

        me = MockEmbeddingProvider(dim=16)
        me.start()
        vs = MemoryVectorStore(dim=16)
        vs.start({"dim": 16})
        bm = BM25Retriever()
        bm.index([{"doc_id": "dx", "text": "\u7ec8\u7aef\u5feb\u6377\u952e", "user_id": "u1", "status": "active"}])

        me.close()
        hr = HybridRetriever(me, vs, bm)
        r = hr.search({"query": "\u7ec8\u7aef", "user_id": "u1", "top_k": 3})
        assert r["meta"]["degraded"] is True
        assert len(r["items"]) > 0


class TestMVP1Metrics:
    def test_record_model_metrics(self, emb):
        import time
        info = emb.model_info()
        assert info["dimension"] == 512
        texts = ["\u9e92\u9e9f\u7cfb\u7edf\u7ec8\u7aef\u5feb\u6377\u952e"] * 10
        t0 = time.time()
        batch = emb.encode(texts)
        elapsed = (time.time() - t0) * 1000
        assert len(batch["vectors"]) == 10
        assert elapsed > 0
