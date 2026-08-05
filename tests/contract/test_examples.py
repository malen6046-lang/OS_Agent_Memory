import json
from pathlib import Path

from contracts.schemas import (
    ConflictResolveRequest,
    EvaluationRunRequest,
    EventIngestRequest,
    ForgetExecuteRequest,
    ForgetPreviewRequest,
    HealthQuery,
    KnowledgeIngestRequest,
    PreferenceExtractRequest,
    PreferenceHistoryQuery,
    PreferenceQuery,
    PromotionRunRequest,
    SearchRequest,
)


def test_all_standard_request_examples_match_contracts():
    path = Path(__file__).parents[2] / "contracts" / "examples.v1.json"
    examples = json.loads(path.read_text(encoding="utf-8"))["examples"]

    EventIngestRequest.model_validate(examples["events_ingest"]["request"])
    PreferenceExtractRequest.model_validate(
        examples["preferences_extract"]["request"]
    )
    PreferenceQuery.model_validate(examples["preferences_get"]["query"])
    PreferenceHistoryQuery.model_validate(
        examples["preferences_history"]["query"]
    )
    KnowledgeIngestRequest.model_validate(examples["knowledge_ingest"]["request"])
    SearchRequest.model_validate(examples["memory_search"]["request"])
    ConflictResolveRequest.model_validate(examples["conflict_resolve"]["request"])
    ForgetPreviewRequest.model_validate(examples["forget_preview"]["request"])
    ForgetExecuteRequest.model_validate(examples["forget_execute"]["request"])
    PromotionRunRequest.model_validate(examples["promotions_run"]["request"])
    HealthQuery.model_validate(examples["health"]["query"])
    EvaluationRunRequest.model_validate(examples["evaluations_run"]["request"])


def test_openapi_contains_all_v11_paths_and_typed_errors(client):
    schema = client.get("/openapi.json").json()
    expected_paths = {
        "/api/v1/events/ingest",
        "/api/v1/preferences/extract",
        "/api/v1/preferences",
        "/api/v1/preferences/{key}/history",
        "/api/v1/knowledge/ingest",
        "/api/v1/memory/search",
        "/api/v1/conflicts/{conflict_id}/resolve",
        "/api/v1/forget/preview",
        "/api/v1/forget/execute",
        "/api/v1/memory/promotions/run",
        "/api/v1/health",
        "/api/v1/evaluations/run",
    }
    compatibility_paths = {
        "/api/v1/preferences/{key}/versions",
        "/api/v1/knowledge",
        "/api/v1/knowledge/conflicts/resolve",
        "/api/v1/memory/{memory_id}",
        "/api/v1/memory/transitions",
    }
    actual_paths = set(schema["paths"])
    assert expected_paths <= actual_paths
    assert compatibility_paths <= actual_paths
    for operations in schema["paths"].values():
        operation = next(iter(operations.values()))
        assert "422" in operation["responses"]
        assert "500" in operation["responses"]
