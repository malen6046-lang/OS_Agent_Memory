"""Tests for KnowledgeService — V1.1 knowledge ingestion and conflict test."""
import pytest
from modules.knowledge_retrieval.knowledge_service import KnowledgeService


class FakeEmbedding:
    def __init__(self, dim=4):
        self._dim = dim
        self._started = True

    def health(self, deep=False):
        return {"provider": "fake", "status": "healthy", "model": "fake", "dimension": self._dim}

    def start(self): return {"provider": "fake", "status": "healthy", "model": "fake", "dimension": self._dim}
    def close(self): pass
    def model_info(self): return {"model_name": "fake", "dimension": self._dim, "provider": "fake", "fingerprint": "fake@4d"}

    def encode(self, texts):
        vectors = [[0.1 * (hash(t) % 100 + j) for j in range(self._dim)] for t in texts]
        return {"vectors": vectors, "dimension": self._dim, "model_name": "fake", "errors": None}


class FakeVectorStore:
    def __init__(self):
        self._data = {}
        self._next_pk = 1

    def start(self, config=None): return {"provider": "fake", "dimension": 4, "status": "healthy"}
    def close(self): self._data.clear()
    def ensure_collection(self, spec): pass

    def upsert(self, items):
        for item in items:
            pk = item["vector_pk"]
            self._data[pk] = item
        return {"upserted": len(items), "errors": None}

    def query(self, request):
        uid = request.get("filter_user_id")
        status = request.get("filter_status", "active")
        results = []
        for pk, item in self._data.items():
            if uid and item.get("user_id") != uid:
                continue
            if status and item.get("status") != status:
                continue
            results.append({"vector_pk": pk, "score": 0.9, "meta": dict(item)})
        return sorted(results, key=lambda x: x["score"], reverse=True)[:request.get("top_k", 10)]

    def delete(self, pks):
        for pk in pks:
            self._data.pop(pk, None)
        return {"deleted": len(pks), "errors": None}


class TestKnowledgeServiceIngest:
    def test_ingest_single_new(self):
        ks = KnowledgeService(FakeEmbedding(), FakeVectorStore(), None)
        result = ks.ingest([{
            "title": "\u9e92\u9e9f\u7ec8\u7aef\u5feb\u6377\u952e",
            "body": "Ctrl+Alt+T \u6253\u5f00\u7ec8\u7aef",
            "user_id": "usr_0",
            "knowledge_type": "workflow",
        }])
        assert result["ingested"] == 1
        assert result["errors"] is None

    def test_ingest_empty_text(self):
        ks = KnowledgeService(FakeEmbedding(), FakeVectorStore(), None)
        result = ks.ingest([{"title": "", "body": "", "user_id": "usr_0"}])
        assert result["ingested"] == 0
        assert result["errors"] is not None

    def test_ingest_batch(self):
        ks = KnowledgeService(FakeEmbedding(), FakeVectorStore(), None)
        records = [
            {"title": f"Knowledge {i}", "body": f"Body {i}", "user_id": "usr_0"}
            for i in range(10)
        ]
        result = ks.ingest(records)
        assert result["ingested"] == 10


class TestKnowledgeServiceConflict:
    def test_classify_duplicate(self):
        ks = KnowledgeService(FakeEmbedding(), FakeVectorStore(), None)
        old = {"memory_id": "mem_1", "content_text": "Ctrl+Alt+T \u6253\u5f00\u7ec8\u7aef", "memory_kind": "semantic"}
        new = {"memory_id": "mem_2", "content_text": "Ctrl+Alt+T \u6253\u5f00\u7ec8\u7aef", "memory_kind": "semantic"}
        decision = ks.classify_conflict(old, new)
        assert decision["relation"] == "duplicate"
        assert decision["strategy"] == "keep_old"

    def test_classify_unrelated(self):
        ks = KnowledgeService(FakeEmbedding(), FakeVectorStore(), None)
        old = {"memory_id": "mem_1", "content_text": "Ctrl+Alt+T \u6253\u5f00\u7ec8\u7aef", "memory_kind": "semantic"}
        new = {"memory_id": "mem_2", "content_text": "\u6570\u636e\u5e93\u5907\u4efd\u7b56\u7565", "memory_kind": "semantic"}
        decision = ks.classify_conflict(old, new)
        assert decision["relation"] == "unrelated"

    def test_classify_contradict(self):
        ks = KnowledgeService(FakeEmbedding(), FakeVectorStore(), None)
        old = {"memory_id": "mem_1", "content_text": "\u65e7\u7248\u7cfb\u7edf\u4f7f\u7528Ctrl+Shift+T\u6253\u5f00\u7ec8\u7aef", "memory_kind": "semantic"}
        new = {"memory_id": "mem_2", "content_text": "\u5df2\u5e9f\u5f03\uff1a\u65e7\u7248\u7cfb\u7edf\u4f7f\u7528Ctrl+Shift+T\u6253\u5f00\u7ec8\u7aef\uff08\u5df2\u66f4\u65b0\u4e3aCtrl+Alt+T\uff09", "memory_kind": "semantic"}
        decision = ks.classify_conflict(old, new)
        assert decision["relation"] == "contradict"

    def test_apply_keep_old(self):
        ks = KnowledgeService(FakeEmbedding(), FakeVectorStore(), None)
        decision = {"old_memory_id": "mem_1", "new_memory_id": "mem_2", "strategy": "keep_old"}
        result = ks.apply_conflict(decision)
        assert result["memory_id"] == "mem_1"

    def test_apply_merge(self):
        ks = KnowledgeService(FakeEmbedding(), FakeVectorStore(), None)
        decision = {"old_memory_id": "mem_1", "new_memory_id": "mem_2", "strategy": "merge"}
        result = ks.apply_conflict(decision)
        assert result["memory_id"] == "mem_2"
        assert "mem_1" in result.get("supersedes", [])
