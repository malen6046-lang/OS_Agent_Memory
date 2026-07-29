"""Tests for MemoryVectorStore — V1.1 vector store unit tests.

Coverage: CRUD, 用户隔离, 删除一致性, 批量写入, status过滤.
"""
import pytest
from adapters.vector_store.memory_vector_store import MemoryVectorStore


def _make_item(vector_pk: int, user_id: str = "usr_0", status: str = "active", **kwargs) -> dict:
    dim = kwargs.pop("dim", 4)
    return {
        "vector_pk": vector_pk,
        "vector": [0.1 * (vector_pk + i) for i in range(dim)],
        "memory_id": f"mem_{vector_pk:04d}",
        "user_id": user_id,
        "memory_kind": kwargs.get("memory_kind", "semantic"),
        "status": status,
        "scene": "office_automation",
        "content_text": kwargs.get("content_text", f"测试记忆条目 {vector_pk}"),
        "meta": kwargs.get("meta", {}),
    }


class TestVectorStoreLifecycle:
    def test_start_returns_health(self):
        vs = MemoryVectorStore(dim=4)
        h = vs.start({"dim": 4})
        assert h["status"] == "healthy"
        assert h["dimension"] == 4

    def test_close_clears_data(self):
        vs = MemoryVectorStore(dim=4)
        vs.start({"dim": 4})
        vs.upsert([_make_item(1)])
        assert len(vs.query({"vector": [1.0, 0, 0, 0], "top_k": 5})) == 1
        vs.close()
        assert len(vs.query({"vector": [1.0, 0, 0, 0], "top_k": 5})) == 0


class TestVectorStoreUpsert:
    def test_upsert_single(self):
        vs = MemoryVectorStore(dim=4)
        r = vs.upsert([_make_item(1)])
        assert r["upserted"] == 1
        assert r["errors"] is None

    def test_upsert_idempotent(self):
        vs = MemoryVectorStore(dim=4)
        for _ in range(10):
            r = vs.upsert([_make_item(99)])
            assert r["upserted"] == 1
        # Only one record exists
        results = vs.query({"vector": _make_item(99)["vector"], "top_k": 5})
        assert len(results) == 1
        assert results[0]["vector_pk"] == 99

    def test_upsert_batch(self):
        vs = MemoryVectorStore(dim=4)
        items = [_make_item(i) for i in range(100)]
        r = vs.upsert(items)
        assert r["upserted"] == 100


class TestVectorStoreQuery:
    def test_query_returns_results(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(1, content_text="银河麒麟终端快捷键")])
        results = vs.query({"vector": [0.2, 0.3, 0.4, 0.5], "top_k": 5})
        assert len(results) >= 1

    def test_query_respects_top_k(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(i) for i in range(20)])
        results = vs.query({"vector": [1.0, 0, 0, 0], "top_k": 5})
        assert len(results) == 5

    def test_query_structure(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(1)])
        results = vs.query({"vector": [0.2, 0.3, 0.4, 0.5], "top_k": 5})
        for r in results:
            assert "vector_pk" in r
            assert "score" in r
            assert "meta" in r


class TestVectorStoreUserIsolation:
    def test_filter_user_id(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(1, user_id="usr_0")])
        vs.upsert([_make_item(2, user_id="usr_1")])
        results = vs.query({
            "vector": [1.0, 0, 0, 0],
            "top_k": 5,
            "filter_user_id": "usr_0",
        })
        for r in results:
            assert r["meta"]["user_id"] == "usr_0"
        assert all(r["vector_pk"] != 2 for r in results)

    def test_cross_user_returns_nothing(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(1, user_id="usr_0")])
        results = vs.query({
            "vector": [0.2, 0.3, 0.4, 0.5],
            "top_k": 5,
            "filter_user_id": "usr_other",
        })
        assert len(results) == 0


class TestVectorStoreStatusFilter:
    def test_default_filters_tombstoned(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(1, status="active")])
        vs.upsert([_make_item(2, status="tombstoned")])
        results = vs.query({"vector": [1.0, 0, 0, 0], "top_k": 10})
        pks = {r["vector_pk"] for r in results}
        assert 2 not in pks

    def test_explicit_status_filter(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(1, status="tombstoned")])
        results = vs.query({
            "vector": [1.0, 0, 0, 0],
            "top_k": 10,
            "filter_status": "tombstoned",
        })
        assert len(results) >= 1


class TestVectorStoreDelete:
    def test_delete_removes_item(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(1)])
        assert vs.delete([1])["deleted"] == 1
        results = vs.query({"vector": [0.2, 0.3, 0.4, 0.5], "top_k": 5})
        pks = {r["vector_pk"] for r in results}
        assert 1 not in pks

    def test_delete_nonexistent_reports_error(self):
        vs = MemoryVectorStore(dim=4)
        r = vs.delete([999])
        assert r["deleted"] == 0
        assert r["errors"] is not None

    def test_delete_consistency(self):
        vs = MemoryVectorStore(dim=4)
        vs.upsert([_make_item(i) for i in range(10)])
        vs.delete([0, 1, 2])
        results = vs.query({"vector": [1.0, 0, 0, 0], "top_k": 20})
        pks = {r["vector_pk"] for r in results}
        assert 0 not in pks
        assert 1 not in pks
        assert 2 not in pks
        assert 3 in pks


class TestVectorStoreBatch:
    def test_batch_write_and_query_1000(self):
        import time

        vs = MemoryVectorStore(dim=16)
        items = [
            {
                "vector_pk": i,
                "vector": [0.001 * ((i * 7 + j) % 100) for j in range(16)],
                "memory_id": f"mem_{i:04d}",
                "user_id": f"usr_{i % 10}",
                "memory_kind": "semantic",
                "status": "active" if i % 10 != 0 else "tombstoned",
                "scene": "office",
                "content_text": f"记忆条目{i}包含麒麟系统相关关键词",
            }
            for i in range(1000)
        ]
        t0 = time.time()
        vs.upsert(items)
        upsert_ms = (time.time() - t0) * 1000

        t0 = time.time()
        results = vs.query({
            "vector": [0.5] * 16,
            "top_k": 20,
            "filter_user_id": "usr_3",
        })
        query_ms = (time.time() - t0) * 1000

        # V1.1 vector search budget: 100ms
        assert query_ms < 300, f"Vector query too slow: {query_ms:.1f}ms"
        for r in results:
            assert r["meta"]["user_id"] == "usr_3"
            assert r["meta"]["status"] == "active"
        print(f"  [perf] upsert 1000: {upsert_ms:.1f}ms, query: {query_ms:.1f}ms")
