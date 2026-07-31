"""端到端检索演示 — V1.1 HybridRetriever with fallback adapters.

This script is self-contained: it uses the deterministic DemoEmbedding so it
always runs without sentence-transformers or Kylin SDK installed.

Usage:
    python examples/retrieval_demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import time
from adapters.vector_store.memory_vector_store import MemoryVectorStore
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever


# ── Deterministic embedding (no external dependency) ─────────────


class DemoEmbedding:
    def __init__(self, dim: int = 16):
        self._dim = dim
        self._started = True

    def start(self) -> dict:
        return {"provider": "demo", "status": "healthy", "model": "demo", "dimension": self._dim, "load_ms": 1}

    def close(self):
        pass

    def health(self, deep: bool = False) -> dict:
        if not self._started:
            return {"provider": "demo", "status": "stopped", "model": "demo", "dimension": 0}
        r = {"provider": "demo", "status": "healthy", "model": "demo", "dimension": self._dim}
        if deep:
            r["deep_ms"] = 1
            r["deep_dim"] = self._dim
        return r

    def model_info(self) -> dict:
        return {"model_name": "demo", "dimension": self._dim, "provider": "demo", "fingerprint": "demo@16d"}

    def encode(self, texts: list[str]) -> dict:
        return {
            "vectors": [[0.01 * (hash(t) % 100 + j) for j in range(self._dim)] for t in texts],
            "dimension": self._dim,
            "model_name": "demo",
            "errors": None,
        }


# ── Sample knowledge base ────────────────────────────────────────


KNOWLEDGE = [
    {"doc_id": "doc_0", "text": "银河麒麟桌面系统中可以通过 Ctrl+Alt+T 快捷键快速打开终端", "user_id": "usr_0", "memory_kind": "semantic", "status": "active"},
    {"doc_id": "doc_1", "text": "系统设置中支持深色主题和浅色主题，在控制面板的外观选项中切换", "user_id": "usr_0", "memory_kind": "semantic", "status": "active"},
    {"doc_id": "doc_2", "text": "麒麟应用商店可以下载常用办公软件如 WPS、 浏览器和通讯工具", "user_id": "usr_0", "memory_kind": "semantic", "status": "active"},
    {"doc_id": "doc_3", "text": "数据库备份应在每天凌晨 2:00 通过 cron 定时任务自动执行", "user_id": "usr_0", "memory_kind": "procedural", "status": "active"},
    {"doc_id": "doc_4", "text": "Python 开发环境建议使用虚拟环境 venv 隔离项目依赖", "user_id": "usr_0", "memory_kind": "semantic", "status": "active"},
    {"doc_id": "doc_5", "text": "屏幕分辨率可以在设置-显示器中调整，支持 1920x1080 等常见分辨率", "user_id": "usr_0", "memory_kind": "semantic", "status": "active"},
    {"doc_id": "doc_6", "text": "用户偏好表格形式展示汇总数据，不喜欢长段落描述", "user_id": "usr_0", "memory_kind": "preference", "status": "active"},
    {"doc_id": "doc_7", "text": "系统快捷键 Super+E 可以快速打开文件管理器", "user_id": "usr_0", "memory_kind": "semantic", "status": "active"},
    {"doc_id": "doc_8", "text": "在终端中使用 apt 命令可以安装和更新系统软件包", "user_id": "usr_0", "memory_kind": "procedural", "status": "active"},
    {"doc_id": "doc_9", "text": "已废弃：旧版系统使用 Ctrl+Shift+T 打开终端（已更新为 Ctrl+Alt+T）", "user_id": "usr_0", "memory_kind": "semantic", "status": "tombstoned"},
]


# ── Main demo ────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("OS Agent Memory — HybridRetriever Demo (V1.1 fallback)")
    print("=" * 60)

    dim = 16
    emb = DemoEmbedding(dim=dim)
    vs = MemoryVectorStore(dim=dim)
    bm25 = BM25Retriever()

    bm25.index(KNOWLEDGE)
    vs_items = []
    for d in KNOWLEDGE:
        vs_items.append({
            "vector_pk": int(d["doc_id"].split("_")[1]),
            "vector": [0.01 * (hash(d["text"]) % 100 + j) for j in range(dim)],
            "memory_id": d["doc_id"],
            "user_id": d["user_id"],
            "memory_kind": d["memory_kind"],
            "status": d["status"],
            "scene": "office_automation",
            "content_text": d["text"],
        })
    vs.upsert(vs_items)

    hr = HybridRetriever(emb, vs, bm25)
    print(f"\n  indexed {len(KNOWLEDGE)} documents (dim={dim})")

    queries = [
        {"query": "怎样打开终端", "user_id": "usr_0", "top_k": 3},
        {"query": "系统外观主题设置", "user_id": "usr_0", "top_k": 3},
        {"query": "数据库备份时间", "user_id": "usr_0", "top_k": 3},
        {"query": "Python开发建议", "user_id": "usr_0", "top_k": 3},
        {"query": "用户喜欢什么格式", "user_id": "usr_0", "top_k": 3},
    ]

    total_ms = 0.0
    for q in queries:
        t0 = time.time()
        resp = hr.search(q)
        elapsed = (time.time() - t0) * 1000
        total_ms += elapsed

        status = "DEGRADED" if resp["meta"]["degraded"] else "OK"
        print(f"\n  Query: {q['query']}")
        print(f"  Status: {status} | {elapsed:.1f}ms | top_k={q['top_k']}")
        for i, r in enumerate(resp["items"]):
            print(f"    #{i+1} [{r['memory_kind']}] score={r['score']:.4f} | {r['content_text'][:50]}...")

    avg_ms = total_ms / len(queries)
    within_budget = avg_ms <= 500
    print(f"\n  Average latency: {avg_ms:.1f}ms (budget: 500ms) {'PASS' if within_budget else 'OVER_BUDGET'}")

    # Degradation test
    print("\n--- Degradation test ---")
    emb.close()
    resp = hr.search({"query": "终端快捷键", "user_id": "usr_0", "top_k": 3})
    print(f"  Embedding stopped, degraded={resp['meta']['degraded']}, results={len(resp['results'])}")

    print("\nDone.")


if __name__ == "__main__":
    main()
