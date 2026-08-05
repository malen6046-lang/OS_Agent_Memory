"""HybridRetriever unit tests — RRF, 降级, 用户隔离, top_k."""
import pytest
from adapters.vector_store.memory_vector_store import MemoryVectorStore
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever


class FakeEmb:
    def __init__(self, dim=4):
        self._dim, self._started = dim, True
    def start(self):
        return {"provider":"f","status":"healthy","model":"f","dimension":self._dim,"load_ms":1}
    def close(self):
        self._started = False
    def health(self, deep=False):
        if not self._started:
            return {"provider":"f","status":"stopped","model":"f","dimension":0}
        r = {"provider":"f","status":"healthy","model":"f","dimension":self._dim}
        if deep:
            r["deep_ms"] = 1; r["deep_dim"] = self._dim
        return r
    def model_info(self):
        return {"model_name":"f","dimension":self._dim,"provider":"f","fingerprint":f"f@{self._dim}d"}
    def encode(self, texts):
        return {"vectors":[[0.01*(hash(t)%100+j) for j in range(self._dim)] for t in texts],
                "dimension":self._dim,"model_name":"f","errors":None}


class FailingEmb(FakeEmb):
    def health(self, deep=False):
        return {"provider":"f","status":"stopped","model":"f","dimension":0}
    def encode(self, texts):
        raise RuntimeError("down")


def _build():
    emb = FakeEmb(4); vs = MemoryVectorStore(4); bm = BM25Retriever()
    return HybridRetriever(emb, vs, bm), emb, vs, bm


def _index(bm, vs, docs):
    for d in docs:
        d.setdefault("status", "active")
    bm.index(docs)
    items = []
    for d in docs:
        parts = d["doc_id"].split("_")
        pk = int(parts[1]) if len(parts) > 1 else int(d["doc_id"][1:]) if d["doc_id"][1:].isdigit() else hash(d["doc_id"]) % 10000
        items.append({"vector_pk": pk,
                      "vector": [0.01*(hash(d["text"])%100+j) for j in range(4)],
                      "memory_id": d["doc_id"], "user_id": d.get("user_id","usr_0"),
                      "memory_kind": d.get("memory_kind","semantic"),
                      "status": d.get("status","active"), "scene": "off", "content_text": d.get("text","")})
    vs.upsert(items)


class TestHybrid:
    def test_search(self):
        hr, _, vs, bm = _build()
        _index(bm, vs, [{"doc_id":"d0","text":"银河麒麟终端快捷键Ctrl+Alt+T","user_id":"u1"},
                        {"doc_id":"d1","text":"深色主题切换在设置外观中","user_id":"u1"}])
        r = hr.search({"query":"怎样打开终端","user_id":"u1","top_k":3})
        assert len(r["items"]) > 0 and r["meta"]["degraded"] is False

    def test_degraded(self):
        emb = FailingEmb(4); vs = MemoryVectorStore(4); bm = BM25Retriever()
        _index(bm, vs, [{"doc_id":"d0","text":"麒麟系统终端快捷键","user_id":"u1"}])
        hr = HybridRetriever(emb, vs, bm)
        r = hr.search({"query":"终端","user_id":"u1","top_k":3})
        assert r["meta"]["degraded"] is True and len(r["items"]) > 0

    def test_user_isolation(self):
        hr, _, vs, bm = _build()
        _index(bm, vs, [{"doc_id":"d0","text":"A终端笔记","user_id":"uA"},
                        {"doc_id":"d1","text":"B终端笔记","user_id":"uB"}])
        r = hr.search({"query":"终端","user_id":"uA","top_k":5})
        assert all("d1" not in rr["memory_id"] for rr in r["items"])

    def test_top_k(self):
        hr, _, vs, bm = _build()
        _index(bm, vs, [{"doc_id":f"d{i}","text":f"测试文档{i}","user_id":"u"} for i in range(10)])
        assert len(hr.search({"query":"测试","user_id":"u","top_k":3})["items"]) == 3
