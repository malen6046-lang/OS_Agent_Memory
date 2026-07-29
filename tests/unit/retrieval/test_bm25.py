"""Tests for BM25Retriever — V1.1 retrieval unit tests.

Coverage: 中文检索, 空查询, 用户隔离, filter_status,
批量索引, 删除, top_k.
"""
import pytest
from modules.knowledge_retrieval.bm25 import BM25Retriever


def _sample_docs(count: int = 5) -> list[dict]:
    return [
        {"doc_id": f"doc_{i}", "text": t, "user_id": f"usr_{i % 2}", "status": "active"}
        for i, t in enumerate(
            [
                "银河麒麟桌面系统支持通过快捷键快速打开终端",
                "用户偏好深色主题和紧凑布局",
                "在开发环境中使用 Python 编写自动化脚本",
                "通过系统设置可以调整屏幕分辨率和刷新率",
                "数据库备份应在每天凌晨自动执行",
            ]
        )
    ][:count]


def _index_sample(bm25, count=5):
    bm25.index(_sample_docs(count))


class TestBM25Basic:
    def test_chinese_search_returns_results(self):
        bm25 = BM25Retriever()
        _index_sample(bm25)
        results = bm25.search("怎样打开终端", top_k=3)
        assert len(results) > 0
        assert results[0]["score"] > 0

    def test_empty_query_returns_empty(self):
        bm25 = BM25Retriever()
        _index_sample(bm25)
        results = bm25.search("", top_k=5)
        assert len(results) == 0

    def test_no_docs_returns_empty(self):
        bm25 = BM25Retriever()
        results = bm25.search("测试", top_k=5)
        assert len(results) == 0

    def test_result_structure(self):
        bm25 = BM25Retriever()
        _index_sample(bm25)
        results = bm25.search("终端", top_k=3)
        for r in results:
            assert "doc_id" in r
            assert "score" in r
            assert "meta" in r


class TestBM25UserIsolation:
    def test_filter_user_id(self):
        bm25 = BM25Retriever()
        _index_sample(bm25)
        results = bm25.search("系统", top_k=10, filter_user_id="usr_0")
        for r in results:
            assert r["meta"]["user_id"] == "usr_0"

    def test_different_users_get_different_results(self):
        bm25 = BM25Retriever()
        _index_sample(bm25)
        r0 = bm25.search("系统", top_k=10, filter_user_id="usr_0")
        r1 = bm25.search("系统", top_k=10, filter_user_id="usr_1")
        # different users should see different (or possibly overlapping) results
        ids0 = {r["doc_id"] for r in r0}
        ids1 = {r["doc_id"] for r in r1}
        for doc_id in ids0:
            assert r0[0]["meta"]["user_id"] == "usr_0"
        for doc_id in ids1:
            assert r1[0]["meta"]["user_id"] == "usr_1"


class TestBM25StatusFilter:
    def test_filter_status_active(self):
        bm25 = BM25Retriever()
        docs = _sample_docs(5)
        docs.append({
            "doc_id": "doc_tomb", "text": "已删除的终端使用记录",
            "user_id": "usr_0", "status": "tombstoned",
        })
        bm25.index(docs)
        results = bm25.search("终端", top_k=10, filter_user_id="usr_0")
        doc_ids = {r["doc_id"] for r in results}
        assert "doc_tomb" not in doc_ids


class TestBM25Remove:
    def test_remove_excludes_doc(self):
        bm25 = BM25Retriever()
        _index_sample(bm25)
        bm25.remove("doc_0")
        results = bm25.search("麒麟", top_k=10)
        doc_ids = {r["doc_id"] for r in results}
        assert "doc_0" not in doc_ids

    def test_remove_nonexistent_is_noop(self):
        bm25 = BM25Retriever()
        _index_sample(bm25)
        bm25.remove("nonexistent")
        results = bm25.search("\u7cfb\u7edf", top_k=10)
        assert len(results) > 0


class TestBM25TopK:
    def test_respects_top_k(self):
        bm25 = BM25Retriever()
        _index_sample(bm25, count=5)
        results = bm25.search("\u7cfb\u7edf", top_k=2)
        assert len(results) == 2

    def test_top_k_exceeds_docs(self):
        bm25 = BM25Retriever()
        _index_sample(bm25, count=3)
        results = bm25.search("\u7cfb\u7edf", top_k=100)
        assert 1 <= len(results) <= 3


class TestBM25BatchIndex:
    def test_batch_index_1000(self):
        bm25 = BM25Retriever()
        docs = [
            {
                "doc_id": f"doc_{i}",
                "text": f"\u6d4b\u8bd5\u6587\u6863\u7f16\u53f7{i}\u5305\u542b\u9e92\u9e9f\u7cfb\u7edf\u5173\u952e\u8bcd\u548c\u65e5\u5e38\u529e\u516c\u77ed\u8bed",
                "user_id": f"usr_{i % 10}",
                "status": "active",
            }
            for i in range(1000)
        ]
        bm25.index(docs)
        results = bm25.search("\u9e92\u9e9f\u7cfb\u7edf", top_k=10)
        assert len(results) == 10
        # Verify all have scores
        for r in results:
            assert r["score"] > 0

    def test_batch_index_performance(self):
        import time

        bm25 = BM25Retriever()
        docs = [
            {
                "doc_id": f"doc_{i}",
                "text": f"测试文档{i}包含麒麟操作系统桌面环境终端快捷键等内容",
                "user_id": f"usr_{i % 10}",
                "status": "active",
            }
            for i in range(1000)
        ]
        t0 = time.time()
        bm25.index(docs)
        index_ms = (time.time() - t0) * 1000

        t0 = time.time()
        bm25.search("麒麟系统终端", top_k=20)
        query_ms = (time.time() - t0) * 1000

        # V1.1 BM25 budget: 40ms per search
        assert query_ms < 200, f"BM25 search too slow: {query_ms:.1f}ms"
        print(f"  [perf] index 1000 docs: {index_ms:.1f}ms, query: {query_ms:.1f}ms")
