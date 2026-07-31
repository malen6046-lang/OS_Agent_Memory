"""KnowledgeService unit tests."""
from modules.knowledge_retrieval.knowledge_service import KnowledgeService


class FakeEmb:
    def __init__(self, dim=4):
        self._dim, self._started = dim, True
    def health(self, deep=False):
        return {"provider":"f","status":"healthy","model":"f","dimension":self._dim}
    def model_info(self):
        return {"model_name":"f","dimension":self._dim,"provider":"f","fingerprint":"f@4d"}
    def encode(self, texts):
        return {"vectors":[[0.1*(hash(t)%100+j) for j in range(self._dim)] for t in texts],
                "dimension":self._dim,"model_name":"f","errors":None}


class FakeVS:
    def __init__(self):
        self._data = {}
    def query(self, request):
        uid = request.get("filter_user_id")
        status = request.get("filter_status", "active")
        r = []
        for pk, item in self._data.items():
            if uid and item.get("user_id") != uid:
                continue
            if status and item.get("status") != status:
                continue
            r.append({"vector_pk": pk, "score": 0.9, "meta": dict(item)})
        return sorted(r, key=lambda x: x["score"], reverse=True)[:request.get("top_k", 10)]
    def upsert(self, items):
        for item in items:
            self._data[item["vector_pk"]] = item
        return {"upserted": len(items), "errors": None}


class TestKS:
    def test_ingest(self):
        ks = KnowledgeService(FakeEmb(), FakeVS(), None)
        r = ks.ingest([{"title":"a","body":"b","user_id":"u","knowledge_type":"workflow"}])
        assert len(r["items"]) == 1

    def test_duplicate(self):
        ks = KnowledgeService(FakeEmb(), FakeVS(), None)
        o = {"memory_id":"m1","content_text":"Ctrl+Alt+T打开终端"}
        n = {"memory_id":"m2","content_text":"Ctrl+Alt+T打开终端"}
        assert ks.classify_conflict(o, n)["relation"] == "duplicate"

    def test_unrelated(self):
        ks = KnowledgeService(FakeEmb(), FakeVS(), None)
        o = {"memory_id":"m1","content_text":"终端快捷键"}
        n = {"memory_id":"m2","content_text":"数据库备份策略"}
        assert ks.classify_conflict(o, n)["relation"] == "unrelated"

    def test_contradict(self):
        ks = KnowledgeService(FakeEmb(), FakeVS(), None)
        o = {"memory_id":"m1","content_text":"旧版使用Ctrl+Shift+T"}
        n = {"memory_id":"m2","content_text":"已废弃旧版已更新为Ctrl+Alt+T"}
        assert ks.classify_conflict(o, n)["relation"] == "contradict"
