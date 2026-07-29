"""Tests for HybridRetriever — V1.1 hybrid retrieval unit tests.

Coverage: 中文检索, 用户隔离, 降级策略, top_k, RRF 融合.
"""
import pytest
from adapters.vector_store.memory_vector_store import MemoryVectorStore
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever


# ── helpers ────────────────────────────────────────────────────


class FakeEmbedding:
    """Deterministic fake embedding for reproducible tests."""

    def __init__(self, dim: int = 4):
        self._dim = dim
        self._started = True
        self._call_count = 0

    def start(self) -> dict:
        self._started = True
        return {"provider": "fake", "status": "healthy", "dimension": self._dim, "model": "fake-test"}

    def close(self) -> None:
        self._started = False

    def health(self, deep: bool = False) -> dict:
        if not self._started:
            return {"provider": "fake", "status": "stopped", "model": "fake-test", "dimension": 0}
        return {"provider": "fake", "status": "healthy", "model": "fake-test", "dimension": self._dim}

    def model_info(self) -> dict:
        return {"model_name": "fake-test", "dimension": self._dim, "provider": "fake", "fingerprint": "fake@4d"}

    def encode(self, texts: list[str]) -> dict:
        self._call_count += 1
        vectors = []
        for t in texts:
            vec = [0.1 * (hash(t) % 100 + i) for i in range(self._dim)]
            vectors.append(vec)
        return {"vectors": vectors, "dimension": self._dim, "model_name": "fake-test", "errors": None}


class FailingEmbedding(FakeEmbedding):
    """Simulates embedding provider failure."""

    def health(self, deep: bool = False) -> dict:
        return {"provider": "fake", "status": "stopped", "model": "fake-test", "dimension": 0}

    def encode(self, texts: list[str]) -> dict:
        raise RuntimeError("embedding unavailable")


def _build_hybrid(dim=4):
    emb = FakeEmbedding(dim=dim)
    vs = MemoryVectorStore(dim=dim)
    bm25 = BM25Retriever()
    return HybridRetriever(emb, vs, bm25), emb, vs, bm25


def _index_docs(bm25: BM25Retriever, vs: MemoryVectorStore, docs: list[dict]) -> None:
    bm25.index(docs)
    vs_items = []
    for d in docs:
        d.setdefault("status", "active")
        vs_items.append({
            "vector_pk": int(d["doc_id"].split("_")[1]),
            "vector": [0.01 * (hash(d["text"]) % 100 + j) for j in range(4)],
            "memory_id": d["doc_id"],
            "user_id": d.get("user_id", "usr_0"),
            "memory_kind": d.get("memory_kind", "semantic"),
            "status": d.get("status", "active"),
            "scene": "office",
            "content_text": d.get("text", ""),
        })
    vs.upsert(vs_items)


# ── tests ──────────────────────────────────────────────────────


class TestHybridBasic:
    def test_chinese_search(self):
        hr, _, vs, bm = _build_hybrid()
        _index_docs(bm, vs, [
            {"doc_id": "doc_0", "text": "银河麒麟系统中可以通过 Ctrl+Alt+T 打开终端", "user_id": "usr_0"},
            {"doc_id": "doc_1", "text": "系统支持深色主题和浅色主题切换", "user_id": "usr_0"},
            {"doc_id": "doc_2", "text": "在应用程序商店中可以下载办公软件", "user_id": "usr_0"},
        ])
        resp = hr.search({"query": "怎样打开终端", "user_id": "usr_0", "top_k": 3})
        assert len(resp["results"]) > 0
        assert resp["meta"]["degraded"] is False
        assert resp["meta"]["elapsed_ms"] >= 0

    def test_response_structure(self):
        hr, _, vs, bm = _build_hybrid()
        _index_docs(bm, vs, [
            {"doc_id": "doc_0", "text": "测试麒麟系统终端", "user_id": "usr_0"},
        ])
        resp = hr.search({"query": "麒麟", "user_id": "usr_0", "top_k": 3})
        for r in resp["results"]:
            assert "memory_id" in r
            assert "score" in r
            assert "memory_kind" in r
            assert "content_text" in r
        assert "elapsed_ms" in resp["meta"]
        assert "degraded" in resp["meta"]
        assert "provider" in resp["meta"]


class TestHybridUserIsolation:
    def test_user_filtering(self):
        hr, _, vs, bm = _build_hybrid()
        _index_docs(bm, vs, [
            {"doc_id": "doc_0", "text": "用户A的麒麟系统终端笔记", "user_id": "usr_A"},
            {"doc_id": "doc_1", "text": "用户B的麒麟系统终端笔记", "user_id": "usr_B"},
        ])
        resp = hr.search({"query": "麒麟终端", "user_id": "usr_A", "top_k": 5})
        memory_ids = {r["memory_id"] for r in resp["results"]}
        assert "doc_1" not in memory_ids, "Should not see user B's document"


class TestHybridDegradation:
    def test_degraded_when_embedding_fails(self):
        failing_emb = FailingEmbedding(dim=4)
        vs = MemoryVectorStore(dim=4)
        bm = BM25Retriever()
        text = "\u9e92\u9e9f\u7cfb\u7edf\u7ec8\u7aef\u5feb\u6377\u952e\u8bf4\u660e"
        _index_docs(bm, vs, [
            {"doc_id": "doc_0", "text": text, "user_id": "usr_0"},
        ])
        hr = HybridRetriever(failing_emb, vs, bm)
        resp = hr.search({"query": "\u7ec8\u7aef", "user_id": "usr_0", "top_k": 3})
        assert resp["meta"]["degraded"] is True
        assert len(resp["results"]) > 0  # BM25 fallback works

    def test_degraded_in_response_when_embedding_unavailable(self):
        hr, _, vs, bm = _build_hybrid()
        _index_docs(bm, vs, [
            {"doc_id": "doc_0", "text": "在银河麒麟桌面中配置开发环境", "user_id": "usr_0"},
        ])
        # Force embedding to fail
        hr._emb = FailingEmbedding()
        resp = hr.search({"query": "开发环境", "user_id": "usr_0", "top_k": 3})
        assert resp["meta"]["degraded"] is True
        assert resp["meta"]["provider"] == "fallback"


class TestHybridTopK:
    def test_respects_top_k(self):
        hr, _, vs, bm = _build_hybrid()
        docs = [
            {"doc_id": f"doc_{i}", "text": f"测试麒麟系统文档{i}包含不同关键词组合", "user_id": "usr_0"}
            for i in range(20)
        ]
        _index_docs(bm, vs, docs)
        resp = hr.search({"query": "麒麟系统", "user_id": "usr_0", "top_k": 5})
        assert len(resp["results"]) == 5


class TestHybridRRF:
    def test_rrf_dedup(self):
        hr, _, vs, bm = _build_hybrid()
        # Index same content so both dense and sparse would match
        _index_docs(bm, vs, [
            {"doc_id": "doc_0", "text": "精准匹配麒麟系统终端快捷键Ctrl+Alt+T", "user_id": "usr_0"},
        ])
        resp = hr.search({"query": "麒麟终端快捷键", "user_id": "usr_0", "top_k": 5})
        memory_ids = [r["memory_id"] for r in resp["results"]]
        # RRF should not return duplicate doc_ids
        assert len(memory_ids) == len(set(memory_ids))
