import inspect
from typing import Any, get_type_hints

import pytest

from contracts.protocols import (
    AuditRepository,
    EmbeddingProvider,
    EvaluationService,
    ForgetService,
    HybridRetriever,
    IdempotencyRepository,
    KnowledgeService,
    MemoryRepository,
    PreferenceService,
    SafetyService,
    VectorStoreAdapter,
)


EXPECTED_METHODS = {
    PreferenceService: ["extract", "upsert", "resolve", "history"],
    KnowledgeService: ["ingest", "classify_conflict", "apply_conflict"],
    HybridRetriever: ["search"],
    ForgetService: ["preview", "execute"],
    SafetyService: ["check"],
    EmbeddingProvider: [
        "start",
        "close",
        "health",
        "model_info",
        "encode",
    ],
    VectorStoreAdapter: [
        "start",
        "close",
        "ensure_collection",
        "upsert",
        "query",
        "delete",
    ],
    MemoryRepository: ["commit_ingest", "get_by_ids", "logical_delete"],
    IdempotencyRepository: ["get", "save"],
    AuditRepository: ["record"],
    EvaluationService: ["run"],
}


@pytest.mark.parametrize("protocol", EXPECTED_METHODS)
def test_contract_type_is_protocol(protocol):
    assert protocol._is_protocol is True


@pytest.mark.parametrize(
    ("protocol", "method_names"), EXPECTED_METHODS.items()
)
def test_protocol_methods_are_present_synchronous_and_fully_typed(
    protocol, method_names
):
    public_methods = [
        name
        for name, value in protocol.__dict__.items()
        if not name.startswith("_") and inspect.isfunction(value)
    ]
    assert public_methods == method_names

    for method_name in method_names:
        method = getattr(protocol, method_name)
        assert inspect.iscoroutinefunction(method) is False
        hints = get_type_hints(method)
        assert "return" in hints
        assert all(annotation is not Any for annotation in hints.values())


def test_repository_and_forget_parameter_order_is_frozen():
    assert list(inspect.signature(MemoryRepository.commit_ingest).parameters) == [
        "self",
        "result",
    ]
    assert list(inspect.signature(MemoryRepository.logical_delete).parameters) == [
        "self",
        "plan",
    ]
    assert list(inspect.signature(MemoryRepository.get_by_ids).parameters) == [
        "self",
        "user_id",
        "memory_ids",
        "statuses",
    ]
    assert list(inspect.signature(ForgetService.execute).parameters) == [
        "self",
        "request",
    ]
    assert list(inspect.signature(IdempotencyRepository.get).parameters) == [
        "self",
        "user_id",
        "operation",
        "idempotency_key",
    ]
