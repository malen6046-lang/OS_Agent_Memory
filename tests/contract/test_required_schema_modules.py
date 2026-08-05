"""V1.2.2 contract-module completeness checks."""

import pytest
from pydantic import BaseModel, ValidationError

from contracts.schemas import evaluation, forget, knowledge, provider, responses, retrieval


REQUIRED_MODELS = {
    knowledge: {
        "KnowledgeCreate",
        "KnowledgeUpdate",
        "KnowledgeMemoryResponse",
        "KnowledgeIngestRequest",
        "KnowledgeIngestItem",
        "KnowledgeIngestResult",
    },
    retrieval: {"SearchFilters", "SearchRequest", "SearchResult", "SearchResponse"},
    forget: {
        "ForgetPreviewRequest",
        "ForgetCandidate",
        "ForgetPlan",
        "ForgetExecuteRequest",
        "ForgetFailedItem",
        "ForgetResult",
    },
    evaluation: {"EvaluationRunRequest", "EvaluationResult"},
    provider: {"ProviderHealth", "EmbeddingModelInfo", "IndexInfo", "EmbeddingBatch"},
    responses: {"ErrorBody", "ResponseMeta", "SuccessResponse", "ErrorResponse"},
}


@pytest.mark.parametrize(
    ("module", "model_names"),
    REQUIRED_MODELS.items(),
    ids=lambda value: getattr(value, "__name__", "required-models"),
)
def test_required_contract_module_exports_buildable_pydantic_v2_models(
    module, model_names
):
    for model_name in model_names:
        model = getattr(module, model_name)
        assert issubclass(model, BaseModel)
        assert model.model_json_schema()["type"] == "object"


def test_search_top_k_rejects_values_outside_frozen_bounds():
    base = {"request_id": "req_schema", "user_id": "usr_schema", "query": "query"}
    for top_k in (0, 101):
        with pytest.raises(ValidationError):
            retrieval.SearchRequest(**base, top_k=top_k)
