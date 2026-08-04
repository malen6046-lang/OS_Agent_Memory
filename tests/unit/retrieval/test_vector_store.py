"""VectorStore unit tests — CRUD, 用户隔离, 删除一致性, 批量."""
import pytest
from adapters.vector_store.memory_vector_store import MemoryVectorStore


def _item(pk, uid="usr_0", status="active", **kw):
    dim = kw.pop("dim", 4)
    return {"vector_pk": pk, "vector": [0.1*(pk+i) for i in range(dim)],
            "memory_id": f"mem_{pk:04d}", "user_id": uid, "memory_kind": kw.get("memory_kind","semantic"),
            "status": status, "scene": "office", "content_text": kw.get("text", f"item {pk}")}


class TestVSBasic:
    def test_start(self):
        h = MemoryVectorStore(4).start({"dim": 4})
        assert h["status"] == "healthy"
    def test_close_clears(self):
        vs = MemoryVectorStore(4); vs.start({"dim": 4}); vs.upsert([_item(1)])
        assert len(vs.query({"vector": [1,0,0,0], "top_k": 5})) == 1
        vs.close()
        assert vs.query({"vector": [1,0,0,0], "top_k": 5}) == []


class TestVSUpsert:
    def test_single(self):
        vs = MemoryVectorStore(4)
        assert vs.upsert([_item(1)])["upserted"] == 1
    def test_idempotent(self):
        vs = MemoryVectorStore(4)
        for _ in range(10): vs.upsert([_item(99)])
        assert len(vs.query({"vector": _item(99)["vector"], "top_k": 5})) == 1
    def test_batch_100(self):
        vs = MemoryVectorStore(4)
        assert vs.upsert([_item(i) for i in range(100)])["upserted"] == 100


class TestVSQuery:
    def test_results(self):
        vs = MemoryVectorStore(4); vs.upsert([_item(1)])
        assert len(vs.query({"vector": [0.2,0.3,0.4,0.5], "top_k": 5})) >= 1
    def test_top_k(self):
        vs = MemoryVectorStore(4); vs.upsert([_item(i) for i in range(20)])
        assert len(vs.query({"vector": [1,0,0,0], "top_k": 5})) == 5


class TestVSIsolation:
    def test_user_filter(self):
        vs = MemoryVectorStore(4)
        vs.upsert([_item(1,"usr_0"), _item(2,"usr_1")])
        r = vs.query({"vector": [1,0,0,0], "top_k": 5, "filter_user_id": "usr_0"})
        assert all(rr["meta"]["user_id"] == "usr_0" for rr in r)
    def test_cross_user_empty(self):
        vs = MemoryVectorStore(4); vs.upsert([_item(1,"usr_0")])
        assert vs.query({"vector": [1,0,0,0], "top_k": 5, "filter_user_id": "usr_x"}) == []


class TestVSStatus:
    def test_tombstoned_filtered(self):
        vs = MemoryVectorStore(4)
        vs.upsert([_item(1,status="active"), _item(2,status="tombstoned")])
        pks = {r["vector_pk"] for r in vs.query({"vector": [1,0,0,0], "top_k": 10})}
        assert 2 not in pks


class TestVSDelete:
    def test_delete(self):
        vs = MemoryVectorStore(4); vs.upsert([_item(1)])
        assert vs.delete([1])["deleted"] == 1
        assert 1 not in {r["vector_pk"] for r in vs.query({"vector": [0.2,0.3,0.4,0.5], "top_k": 5})}
    def test_consistency(self):
        vs = MemoryVectorStore(4); vs.upsert([_item(i) for i in range(10)]); vs.delete([0,1,2])
        pks = {r["vector_pk"] for r in vs.query({"vector": [1,0,0,0], "top_k": 20})}
        assert not {0,1,2} & pks and 3 in pks


class TestVSBatch:
    def test_1000(self):
        vs = MemoryVectorStore(16)
        items = [{"vector_pk": i, "vector": [0.001*((i*7+j)%100) for j in range(16)],
                  "memory_id": f"mem_{i:04d}", "user_id": f"usr_{i%10}",
                  "memory_kind": "semantic", "status": "active" if i%10 else "tombstoned",
                  "scene": "office", "content_text": f"memory {i}"} for i in range(1000)]
        vs.upsert(items)
        r = vs.query({"vector": [0.5]*16, "top_k": 20, "filter_user_id": "usr_3"})
        assert all(rr["meta"]["user_id"] == "usr_3" for rr in r)
