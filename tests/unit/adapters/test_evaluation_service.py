from contracts.schemas.evaluation import EvaluationRunRequest

from adapters.evaluation import offline_service


def test_offline_evaluation_service_runs_existing_runner(monkeypatch):
    monkeypatch.setitem(
        offline_service.TASK_RUNNERS,
        "retrieval",
        lambda *, split: {
            "mrr": 0.75,
            "recall_at_k": {"5": 0.8},
            "split": split,
            "status": "baseline_not_competition_claim",
        },
    )

    result = offline_service.OfflineEvaluationService().run(
        EvaluationRunRequest(
            request_id="req_eval_1",
            metric_names=["retrieval.mrr", "retrieval.recall_at_k.5"],
            dataset={"split": "dev", "tasks": ["retrieval"]},
        )
    )

    assert result.request_id == "req_eval_1"
    assert result.status == "completed"
    assert result.metrics == {
        "retrieval.mrr": 0.75,
        "retrieval.recall_at_k.5": 0.8,
    }
    assert result.created_at.tzinfo is not None


def test_offline_evaluation_service_marks_unknown_metric_failed(monkeypatch):
    monkeypatch.setitem(
        offline_service.TASK_RUNNERS,
        "retrieval",
        lambda *, split: {"mrr": 0.75},
    )

    result = offline_service.OfflineEvaluationService().run(
        EvaluationRunRequest(
            request_id="req_eval_2",
            metric_names=["retrieval.unknown"],
            dataset={"split": "dev", "tasks": ["retrieval"]},
        )
    )

    assert result.status == "failed"
    assert result.metrics == {}


def test_offline_evaluation_service_rejects_unknown_split():
    result = offline_service.OfflineEvaluationService().run(
        EvaluationRunRequest(
            request_id="req_eval_3",
            metric_names=["retrieval.mrr"],
            dataset={"split": "invalid", "tasks": ["retrieval"]},
        )
    )

    assert result.status == "failed"
    assert result.metrics == {}
