"""ConflictClassifier dedicated tests — V1.1 six-way classification."""
from modules.knowledge_retrieval.conflict_classifier import ConflictClassifier


class TestSixWayClassification:
    def test_duplicate_same_text(self):
        cc = ConflictClassifier()
        r = cc.classify("\u7ec8\u7aef\u5feb\u6377\u952e", {},
                        [{"score": 0.95, "meta": {"memory_id": "m1", "content_text": "\u7ec8\u7aef\u5feb\u6377\u952e"}}])
        assert r["relation"] == "duplicate"
        assert r["conflict"] is False

    def test_unrelated_low_similarity(self):
        cc = ConflictClassifier()
        r = cc.classify("\u6570\u636e\u5e93\u5907\u4efd\u7b56\u7565", {},
                        [{"score": 0.3, "meta": {"memory_id": "m1", "content_text": "\u7ec8\u7aef\u5feb\u6377\u952e"}}])
        assert r["relation"] == "unrelated"

    def test_contradict_negation(self):
        cc = ConflictClassifier()
        r = cc.classify("\u5df2\u5e9f\u5f03\uff1a\u65e7\u7248\u4f7f\u7528Ctrl+Shift+T\u6253\u5f00\u7ec8\u7aef\uff08\u5df2\u66f4\u65b0\u4e3aCtrl+Alt+T\uff09", {},
                        [{"score": 0.90, "meta": {"memory_id": "m1",
                         "content_text": "\u65e7\u7248\u4f7f\u7528Ctrl+Shift+T\u6253\u5f00\u7ec8\u7aef"}}])
        assert r["relation"] == "contradict"
        assert r["strategy"] == "manual_review"

    def test_replace_newer_timestamp(self):
        cc = ConflictClassifier()
        r = cc.classify(
            "\u7ec8\u7aef\u5feb\u6377\u952e\u66f4\u65b0\u4e3aCtrl+Alt+T",
            {"valid_from": "2026-08-01"},
            [{"score": 0.90, "meta": {"memory_id": "m1",
             "content_text": "\u7ec8\u7aef\u5feb\u6377\u952eCtrl+Shift+T",
             "valid_from": "2025-01-01"}}])
        assert r["relation"] == "replace"
        assert r["strategy"] == "keep_new"
        assert r["conflict"] is True

    def test_extend_complementary_info(self):
        cc = ConflictClassifier()
        r = cc.classify(
            "\u7ec8\u7aef\u5feb\u6377\u952eCtrl+Alt+T\uff0c\u65b0\u7248\u4e5f\u652f\u6301Super+T",
            {},
            [{"score": 0.90, "meta": {"memory_id": "m1",
             "content_text": "\u7ec8\u7aef\u5feb\u6377\u952eCtrl+Alt+T"}}])
        assert r["relation"] == "extend"
        assert r["strategy"] == "merge"
        assert r["conflict"] is True

    def test_no_similar_entries(self):
        cc = ConflictClassifier()
        r = cc.classify("new knowledge", {}, [])
        assert r["relation"] == "unrelated"
        assert r["conflict"] is False
        assert r["new_version"] == 1

    def test_below_threshold_not_conflict(self):
        cc = ConflictClassifier()
        # 0.84 is below 0.85 threshold
        r = cc.classify("different thing", {},
                        [{"score": 0.84, "meta": {"memory_id": "m1", "content_text": "other content"}}])
        assert r["relation"] == "unrelated"
        assert r["conflict"] is False
