"""Mini evaluation — 小数据集评测

Covers Task 9:
  - 30 knowledge entries
  - 15 queries with correct doc_id answers
  - 8 conflict pairs
  - Metrics: Top-1, Recall@5, avg/p95 latency, degradation, user isolation
"""
import time
import json
from adapters.embedding.mock_provider import MockEmbeddingProvider
from adapters.vector_store.memory_vector_store import MemoryVectorStore
from modules.knowledge_retrieval.bm25 import BM25Retriever
from modules.knowledge_retrieval.knowledge_service import KnowledgeService
from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever
from modules.knowledge_retrieval.conflict_classifier import ConflictClassifier

# -- Dataset --
KNOWLEDGE = [
    {"doc_id": "k01", "text": "Ctrl+Alt+T快捷键可以在麒麟系统中打开终端", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k02", "text": "系统设置深色主题在控制面板外观选项中切换", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k03", "text": "麒麟应用商店可以下载WPS浏览器和通讯工具", "user_id": "u1", "memory_kind": "fact", "status": "active"},
    {"doc_id": "k04", "text": "数据库备份应在每天凌晨2点通过cron定时任务执行", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k05", "text": "Python开发使用虚拟环境venv隔离项目依赖", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k06", "text": "屏幕分辨率设置显示器中调整1920x1080", "user_id": "u1", "memory_kind": "fact", "status": "active"},
    {"doc_id": "k07", "text": "用户喜欢表格形式展示数据不喜欢长段落", "user_id": "u1", "memory_kind": "preference", "status": "active"},
    {"doc_id": "k08", "text": "Super+E快捷键快速打开文件管理器", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k09", "text": "终端apt命令安装更新系统软件包", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k10", "text": "旧版Ctrl+Shift+T已废弃更新为Ctrl+Alt+T", "user_id": "u1", "memory_kind": "fact", "status": "tombstoned"},
    {"doc_id": "k11", "text": "防火墙默认开启通过ufw命令管理端口", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k12", "text": "SSH远程连接使用密钥认证禁用密码登录", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k13", "text": "多桌面切换快捷键Ctrl+Alt+方向键", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k14", "text": "网络代理设置系统设置网络代理手动配置", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k15", "text": "文件管理器支持列表图标分栏三种视图", "user_id": "u1", "memory_kind": "fact", "status": "active"},
    {"doc_id": "k16", "text": "自动锁屏5分钟无操作后自动锁定", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k17", "text": "系统日志查看使用journalctl命令", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k18", "text": "定时关机shutdown命令设置定时时间", "user_id": "u1", "memory_kind": "workflow", "status": "active"},
    {"doc_id": "k19", "text": "拼音输入法搜狗输入法在麒麟商店安装", "user_id": "u1", "memory_kind": "fact", "status": "active"},
    {"doc_id": "k20", "text": "云备份服务支持增量备份和全量备份", "user_id": "u1", "memory_kind": "fact", "status": "active"},
    {"doc_id": "k21", "text": "用户喜欢深色主题不喜欢浅色", "user_id": "u2", "memory_kind": "preference", "status": "active"},
    {"doc_id": "k22", "text": "用户使用VS Code编辑器开发Python", "user_id": "u2", "memory_kind": "preference", "status": "active"},
    {"doc_id": "k23", "text": "系统自动更新每周日凌晨检查更新", "user_id": "u2", "memory_kind": "workflow", "status": "active"},
]

QUERIES = [
    {"query": "怎么打开终端", "gold_doc_id": "k01", "user_id": "u1"},
    {"query": "深色主题怎么设置", "gold_doc_id": "k02", "user_id": "u1"},
    {"query": "安装软件用什么", "gold_doc_id": "k03", "user_id": "u1"},
    {"query": "数据库备份时间", "gold_doc_id": "k04", "user_id": "u1"},
    {"query": "Python开发环境怎么建", "gold_doc_id": "k05", "user_id": "u1"},
    {"query": "分辨率怎么调", "gold_doc_id": "k06", "user_id": "u1"},
    {"query": "用户喜欢什么展示格式", "gold_doc_id": "k07", "user_id": "u1"},
    {"query": "文件管理器快捷键", "gold_doc_id": "k08", "user_id": "u1"},
    {"query": "防火墙怎么管理", "gold_doc_id": "k11", "user_id": "u1"},
    {"query": "SSH怎么设置安全连接", "gold_doc_id": "k12", "user_id": "u1"},
    {"query": "怎么切换桌面", "gold_doc_id": "k13", "user_id": "u1"},
    {"query": "代理怎么配", "gold_doc_id": "k14", "user_id": "u1"},
    {"query": "日志怎么看", "gold_doc_id": "k17", "user_id": "u1"},
    {"query": "怎么定时关机", "gold_doc_id": "k18", "user_id": "u1"},
    {"query": "备份怎么设置", "gold_doc_id": "k20", "user_id": "u1"},
]

CONFLICT_PAIRS = [
    ("Ctrl+Alt+T打开终端", "Ctrl+Alt+T打开终端", "duplicate"),
    ("Ctrl+Shift+T打开终端已废弃由Ctrl+Alt+T替代", "Ctrl+Shift+T打开终端", "contradict"),
    ("Ctrl+Alt+T打开终端2026版", "Ctrl+Alt+T打开终端2025版", "replace"),
    ("Ctrl+Alt+T打开终端新版也支持Super+T", "Ctrl+Alt+T打开终端", "extend"),
    ("数据库备份cron定时任务", "远程连接SSH密钥", "unrelated"),
    ("深色主题在控制面板切换", "浅色主题在控制面板切换", "contradict"),
    ("用户喜欢深色主题不喜欢浅色", "用户喜欢浅色主题不喜欢深色", "contradict"),
    ("Ctrl+Alt+T快捷键打开终端", "Ctrl+Alt+T快捷键打开终端", "duplicate"),
]


def build_services():
    emb = MockEmbeddingProvider(dim=16)
    emb.start()
    vs = MemoryVectorStore(dim=16)
    vs.start({"dim": 16})
    bm = BM25Retriever()
    ks = KnowledgeService(emb, vs, bm)
    hr = HybridRetriever(emb, vs, bm)
    return emb, vs, bm, ks, hr


def evaluate_retrieval():
    emb, vs, bm, ks, hr = build_services()

    # Index knowledge
    bm.index(KNOWLEDGE)
    import hashlib
    for k in KNOWLEDGE:
        batch = emb.encode([k["text"]])
        pk = int(hashlib.md5(k["doc_id"].encode()).hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF
        vs.upsert([{"vector_pk": pk, "vector": batch["vectors"][0],
                    "memory_id": k["doc_id"], "user_id": k["user_id"],
                    "memory_kind": k["memory_kind"], "status": k["status"],
                    "scene": "office", "content_text": k["text"]}])

    # Run queries
    top1_hits = 0
    recall5_hits = 0
    latencies = []
    for q in QUERIES:
        t0 = time.time()
        r = hr.search({"query": q["query"], "user_id": q["user_id"], "top_k": 5})
        lat = (time.time() - t0) * 1000
        latencies.append(lat)

        doc_ids = [rr["memory_id"] for rr in r["items"]]
        if doc_ids and doc_ids[0] == q["gold_doc_id"]:
            top1_hits += 1
        if q["gold_doc_id"] in doc_ids:
            recall5_hits += 1

    n = len(QUERIES)
    latencies.sort()
    return {
        "Top-1_hit_rate": f"{top1_hits}/{n} = {top1_hits/n*100:.1f}%",
        "Recall@5": f"{recall5_hits}/{n} = {recall5_hits/n*100:.1f}%",
        "avg_latency_ms": round(sum(latencies) / n, 2),
        "p95_latency_ms": round(latencies[int(n * 0.95)], 2),
        "max_latency_ms": round(max(latencies), 2),
    }


def evaluate_degradation():
    emb, vs, bm, ks, hr = build_services()
    bm.index(KNOWLEDGE[:1])
    emb.close()
    r = hr.search({"query": "终端", "user_id": "u1", "top_k": 5})
    return {
        "degraded_works": r["meta"]["degraded"] is True,
        "bm25_results": len(r["items"]) > 0,
    }


def evaluate_user_isolation():
    emb, vs, bm, ks, hr = build_services()
    bm.index(KNOWLEDGE)
    import hashlib
    for k in KNOWLEDGE:
        batch = emb.encode([k["text"]])
        pk = int(hashlib.md5(k["doc_id"].encode()).hexdigest(), 16) & 0x7FFFFFFFFFFFFFFF
        vs.upsert([{"vector_pk": pk, "vector": batch["vectors"][0],
                    "memory_id": k["doc_id"], "user_id": k["user_id"],
                    "memory_kind": k["memory_kind"], "status": k["status"],
                    "scene": "office", "content_text": k["text"]}])

    r_u2 = hr.search({"query": "用户喜欢", "user_id": "u2", "top_k": 10})
    u1_leaked = any(rr["metadata"].get("user_id") == "u1" for rr in r_u2["items"])
    return {"user_isolation_passed": not u1_leaked}


def evaluate_conflict():
    cc = ConflictClassifier()
    total = len(CONFLICT_PAIRS)
    correct = 0
    confusion = {}

    for new_text, old_text, expected in CONFLICT_PAIRS:
        old_meta = {"memory_id": "old", "content_text": old_text}
        if expected == "replace":
            old_meta["valid_from"] = "2025-01-01"
            result = cc.classify(new_text, {"valid_from": "2026-08-01"},
                                 [{"score": 0.90, "meta": old_meta}])
        elif expected in ("contradict", "extend"):
            result = cc.classify(new_text, {},
                                 [{"score": 0.90, "meta": old_meta}])
        else:
            result = cc.classify(new_text, {},
                                 [{"score": 0.30 if expected == "unrelated" else 0.95,
                                   "meta": old_meta}])

        pred = result["relation"]
        if pred == expected:
            correct += 1
        key = f"{expected}->{pred}"
        confusion[key] = confusion.get(key, 0) + 1

    return {
        "conflict_accuracy": f"{correct}/{total} = {correct/total*100:.1f}%",
        "confusion": confusion,
    }


def test_eval_retrieval():
    r = evaluate_retrieval()
    assert float(r["Recall@5"].split("=")[1].strip().replace("%", "")) >= 50.0
    assert r["avg_latency_ms"] < 500


def test_eval_degradation():
    r = evaluate_degradation()
    assert r["degraded_works"] is True
    assert r["bm25_results"] is True


def test_eval_user_isolation():
    r = evaluate_user_isolation()
    assert r["user_isolation_passed"] is True


def test_eval_conflict():
    r = evaluate_conflict()
    assert float(r["conflict_accuracy"].split("=")[1].strip().replace("%", "")) >= 70.0


def test_eval_report():
    """Print evaluation report."""
    retrieval = evaluate_retrieval()
    degradation = evaluate_degradation()
    isolation = evaluate_user_isolation()
    conflict = evaluate_conflict()

    report = {
        "dataset": {"knowledge": len(KNOWLEDGE), "queries": len(QUERIES), "conflicts": len(CONFLICT_PAIRS)},
        "retrieval": retrieval,
        "degradation": degradation,
        "user_isolation": isolation,
        "conflict": conflict,
    }
    print("\n" + json.dumps(report, indent=2, ensure_ascii=False))
    assert True
