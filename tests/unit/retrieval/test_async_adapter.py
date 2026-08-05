"""Async adapter tests — sync algorithm wrapped for async orchestrator."""
import pytest
from adapters.embedding.mock_provider import MockEmbeddingProvider
from adapters.vector_store.memory_vector_store import MemoryVectorStore
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.knowledge_service import KnowledgeService
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever
from modules.knowledge_retrieval.async_adapter import (
    AsyncKnowledgeServiceAdapter,
    AsyncHybridRetrieverAdapter,
    normalize_request,
)


def _build():
    emb = MockEmbeddingProvider(dim=16)
    emb.start()
    vs = MemoryVectorStore(dim=16)
    vs.start({"dim": 16})
    bm = BM25Retriever()
    ks = KnowledgeService(emb, vs, bm)
    hr = HybridRetriever(emb, vs, bm)
    return emb, vs, bm, ks, hr


class TestNormalizeRequest:
    def test_dict_passthrough(self):
        assert normalize_request({"query": "x"}) == {"query": "x"}

    def test_payload_extraction(self):
        r = normalize_request({"query": "x", "payload": {"query": "y"}})
        assert r["query"] == "y"

    def test_pydantic_like(self):
        class Req:
            def model_dump(self):
                return {"query": "z"}
        assert normalize_request(Req()) == {"query": "z"}


class TestAsyncKnowledgeService:
    @pytest.mark.asyncio
    async def test_ingest(self):
        _, _, _, ks, _ = _build()
        adapter = AsyncKnowledgeServiceAdapter(ks)
        event = {
            "user_id": "usr_0",
            "scene": "office",
            "request_id": "req_1",
            "payload": {"title": "test", "body": "body", "knowledge_type": "fact"},
        }
        result = await adapter.ingest(event)
        assert len(result["items"]) == 1
        assert result["items"][0]["status"] in ("inserted", "conflict")

    @pytest.mark.asyncio
    async def test_ingest_records_list(self):
        _, _, _, ks, _ = _build()
        adapter = AsyncKnowledgeServiceAdapter(ks)
        event = {
            "user_id": "usr_0",
            "payload": {
                "records": [
                    {"title": "a", "body": "1", "knowledge_type": "fact"},
                    {"title": "b", "body": "2", "knowledge_type": "fact"},
                ]
            },
        }
        result = await adapter.ingest(event)
        assert len(result["items"]) == 2


class TestAsyncHybridRetriever:
    @pytest.mark.asyncio
    async def test_search(self):
        emb, vs, bm, _, hr = _build()
        bm.index([{"doc_id": "d0", "text": "麒麟系统终端快捷键", "user_id": "u1", "status": "active"}])
        import hashlib
        vec = emb.encode(["麒麟系统终端快捷键"])["vectors"][0]
        pk = int(hashlib.md5(b"d0").hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF
        vs.upsert([{"vector_pk": pk, "vector": vec, "memory_id": "d0", "user_id": "u1",
                    "memory_kind": "semantic", "status": "active", "scene": "office",
                    "content_text": "麒麟系统终端快捷键"}])
        adapter = AsyncHybridRetrieverAdapter(hr)
        result = await adapter.search({"query": "终端", "user_id": "u1", "top_k": 5})
        assert len(result["items"]) > 0
