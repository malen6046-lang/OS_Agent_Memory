"""Mini evaluation tests — verify evaluation programs work."""
from evaluation.retrieval_eval import evaluate_retrieval, KNOWLEDGE, QUERIES
from evaluation.conflict_eval import evaluate_conflict, CONFLICT_PAIRS


def test_eval_retrieval():
    r = evaluate_retrieval()
    assert float(r["Recall@5"].split("=")[1].strip().replace("%", "")) >= 50.0
    assert r["avg_latency_ms"] < 500


def test_eval_conflict():
    r = evaluate_conflict()
    assert float(r["conflict_accuracy"].split("=")[1].strip().replace("%", "")) >= 88.0


def test_eval_dataset():
    assert len(KNOWLEDGE) >= 20
    assert len(QUERIES) >= 10
    assert len(CONFLICT_PAIRS) >= 5
