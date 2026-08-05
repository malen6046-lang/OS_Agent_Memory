"""BM25 unit tests — 中文检索, 空查询, 用户隔离, 删除, top_k, 批量."""
import pytest
from modules.knowledge_retrieval.bm25 import BM25Retriever


def _sample_docs(count=5):
    texts = [
        "银河麒麟桌面系统支持通过快捷键快速打开终端",
        "用户偏好深色主题和紧凑布局",
        "在开发环境中使用 Python 编写自动化脚本",
        "通过系统设置可以调整屏幕分辨率和刷新率",
        "数据库备份应在每天凌晨自动执行",
    ]
    return [{"doc_id": f"doc_{i}", "text": t, "user_id": f"usr_{i%2}", "status": "active"}
            for i, t in enumerate(texts[:count])]


class TestBM25Basic:
    def test_chinese_search(self):
        bm = BM25Retriever(); bm.index(_sample_docs(5))
        assert len(bm.search("怎样打开终端", top_k=3)) > 0
    def test_empty_query(self):
        bm = BM25Retriever(); bm.index(_sample_docs(5))
        assert bm.search("") == []
    def test_no_docs(self):
        assert BM25Retriever().search("test") == []
    def test_result_structure(self):
        bm = BM25Retriever(); bm.index(_sample_docs(5))
        for r in bm.search("终端", top_k=3):
            assert "doc_id" in r and "score" in r and "meta" in r


class TestBM25Isolation:
    def test_filter_user_id(self):
        bm = BM25Retriever(); bm.index(_sample_docs(5))
        for r in bm.search("系统", filter_user_id="usr_0"):
            assert r["meta"]["user_id"] == "usr_0"
    def test_status_filter(self):
        bm = BM25Retriever()
        docs = _sample_docs(5)
        docs.append({"doc_id":"dt","text":"已删除内容","user_id":"usr_0","status":"tombstoned"})
        bm.index(docs)
        assert all(r["doc_id"] != "dt" for r in bm.search("删除", top_k=10))


class TestBM25Remove:
    def test_remove(self):
        bm = BM25Retriever(); bm.index(_sample_docs(5)); bm.remove("doc_0")
        assert all(r["doc_id"] != "doc_0" for r in bm.search("麒麟", top_k=10))
    def test_remove_nonexistent(self):
        bm = BM25Retriever(); bm.index(_sample_docs(5)); bm.remove("no")
        assert len(bm.search("系统", top_k=10)) > 0


class TestBM25TopK:
    def test_respects_top_k(self):
        bm = BM25Retriever(); bm.index(_sample_docs(5))
        assert len(bm.search("系统", top_k=2)) == 2


class TestBM25Batch:
    def test_batch_1000(self):
        bm = BM25Retriever()
        docs = [{"doc_id": f"doc_{i}", "text": f"测试文档编号{i}包含麒麟系统关键词",
                 "user_id": f"usr_{i%10}", "status": "active"} for i in range(1000)]
        bm.index(docs)
        r = bm.search("麒麟系统", top_k=10)
        assert len(r) == 10
