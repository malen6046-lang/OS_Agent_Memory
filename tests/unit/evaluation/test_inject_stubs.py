# -*- coding: utf-8 -*-
from evaluation.inject_stubs import (
    wrap_conflict_classify,
    wrap_forget_preview,
    wrap_knowledge_search,
    wrap_preference_service,
    wrap_safety_detect,
)


def test_wrap_none_keeps_baseline() -> None:
    assert wrap_preference_service(None) is None
    assert wrap_knowledge_search(None) is None
    assert wrap_conflict_classify(None) is None
    assert wrap_forget_preview(None) is None
    assert wrap_safety_detect(None) is None


def test_wrap_preference_extract_from_case() -> None:
    class Svc:
        def extract_from_case(self, case):
            return [{"preference_key": "k", "value": "v"}]

    fn = wrap_preference_service(Svc())
    assert fn is not None
    assert fn({"case_id": "x"})[0]["preference_key"] == "k"


def test_wrap_search_normalizes_list() -> None:
    class Svc:
        def search(self, req):
            return ["mem_a", {"memory_id": "mem_b"}]

    fn = wrap_knowledge_search(Svc())
    assert fn is not None
    out = fn({"query": "q", "user_id": "u"})
    assert [r["memory_id"] for r in out["results"]] == ["mem_a", "mem_b"]
