"""Deterministic, side-effect-free service implementations for development."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

from contracts.schemas.common import MemoryStatus
from contracts.schemas.envelope import Envelope
from contracts.schemas.evaluation import EvaluationRun
from contracts.schemas.forget import ForgetExecutionPlan, ForgetPlan
from contracts.schemas.knowledge import IngestResult
from contracts.schemas.memory import MemoryRecord
from contracts.schemas.persistence import (
    AuditResult,
    IdempotencyEntry,
    IngestCommitResult,
    LogicalDeleteResult,
)
from contracts.schemas.provider import (
    DeleteResult,
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderHealth,
    UpsertResult,
    VectorHit,
    VectorItem,
    VectorQuery,
)
from contracts.schemas.retrieval import SearchHit, SearchRequest, SearchResponse
from contracts.schemas.safety import SafetyCheckResult


class MockPreferenceService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def extract(self, events: Any) -> Any:
        self.calls.append(("extract", events))
        if isinstance(events, list):
            return []
        return {"preferences": [], "mock": True}

    def upsert(self, candidates: list[Any]) -> list[Any]:
        self.calls.append(("upsert", candidates))
        return []

    def resolve(
        self, user_id: str, scene: str, keys: list[str] | None = None
    ) -> list[Any]:
        self.calls.append(("resolve", (user_id, scene, keys)))
        return []

    def history(self, user_id: str, preference_key: str) -> list[Any]:
        self.calls.append(("history", (user_id, preference_key)))
        return []


class MockSafetyService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def check(self, request: Any) -> Any:
        self.calls.append(("check", request))
        if isinstance(request, Envelope):
            return SafetyCheckResult(allowed=True)
        return {"allowed": True, "mock": True}


class MockKnowledgeService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any, Any]] = []

    def ingest(self, event: Any, preference_result: Any) -> Any:
        self.calls.append(("ingest", event, preference_result))
        if isinstance(event, list):
            return IngestResult(
                records=[_memory_from_event(item) for item in event]
            )
        return {"records": [], "mock": True}

    def classify_conflict(self, old: Any, new: Any) -> Any:
        raise NotImplementedError("mock conflict classification is not configured")

    def apply_conflict(self, decision: Any) -> Any:
        raise NotImplementedError("mock conflict application is not configured")


class MockRetriever:
    def __init__(
        self,
        embedding_provider: Any = None,
        vector_store: Any = None,
        memory_repository: Any = None,
    ) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.memory_repository = memory_repository

    def search(self, request: Any) -> Any:
        self.calls.append(("search", request))
        if isinstance(request, SearchRequest):
            if (
                self.embedding_provider is not None
                and self.vector_store is not None
                and self.memory_repository is not None
            ):
                batch = self.embedding_provider.encode([request.query])
                vector_hits = self.vector_store.query(
                    VectorQuery(
                        user_id=request.user_id,
                        status=MemoryStatus.ACTIVE,
                        vector=batch.vectors[0],
                        top_k=request.top_k,
                        timeout_ms=500,
                        filters=request.filters,
                    )
                )
                records = self.memory_repository.get_by_ids(
                    request.user_id,
                    [hit.memory_id for hit in vector_hits],
                    [MemoryStatus.ACTIVE],
                )
                records_by_id = {
                    record.memory_id: record for record in records
                }
                items = [
                    SearchHit(
                        memory_id=hit.memory_id,
                        user_id=hit.user_id,
                        status=hit.status,
                        content_text=records_by_id[hit.memory_id].content_text,
                        score=hit.score,
                        attributes=records_by_id[hit.memory_id].attributes,
                    )
                    for hit in vector_hits
                    if hit.memory_id in records_by_id
                ]
                return SearchResponse(
                    request_id=request.request_id,
                    user_id=request.user_id,
                    items=items,
                    total=len(items),
                    provider="mock",
                )
            return SearchResponse(
                request_id=request.request_id,
                user_id=request.user_id,
                items=[],
                total=0,
                provider="mock",
            )
        return {"items": [], "mock": True}


class MockForgetService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def preview(self, request: Any) -> Any:
        self.calls.append(("preview", request))
        if hasattr(request, "request_id"):
            memory_ids = list(getattr(request, "memory_ids", []))
            return ForgetPlan(
                plan_id="forget_mock_plan",
                user_id=request.user_id,
                candidates=[
                    {
                        "memory_id": memory_id,
                        "user_id": request.user_id,
                    }
                    for memory_id in memory_ids
                ],
                risk_level="low",
                confirmation_token="confirm_mock",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        return {
            "plan_id": "forget_mock_plan",
            "memory_ids": _request_value(request, "memory_ids", []),
            "requires_confirmation": True,
            "mock": True,
        }

    def execute(self, request: Any) -> Any:
        self.calls.append(("execute", request))
        if hasattr(request, "request_id"):
            return ForgetExecutionPlan(
                request_id=request.request_id,
                user_id=request.user_id,
                plan_id=request.plan_id,
                memory_ids=list(request.selected_ids),
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            )
        return {
            "plan_id": _request_value(request, "plan_id", "forget_mock_plan"),
            "status": "executed",
            "mock": True,
        }


class MockEmbeddingProvider:
    """Deterministic lifecycle stub matching the V1.1 provider surface."""

    provider_name = "mock"

    def __init__(self, model_name: str = "default") -> None:
        self.model_name = model_name
        self.started = False
        self.closed = False
        self.lifecycle_events: list[str] = []

    def start(self) -> ProviderHealth:
        self.lifecycle_events.append("embedding.start")
        self.started = True
        self.closed = False
        return self.health()

    def close(self) -> None:
        self.lifecycle_events.append("embedding.close")
        self.closed = True
        self.started = False

    def health(self, deep: bool = False) -> ProviderHealth:
        return ProviderHealth(
            provider=self.provider_name,
            status="ok" if self.started else "stopped",
            details={"deep": deep},
        )

    def model_info(self) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider=self.provider_name,
            model_name=self.model_name,
            dimension=8,
        )

    def encode(self, texts: list[str]) -> EmbeddingBatch:
        return EmbeddingBatch(
            vectors=[_deterministic_vector(text) for text in texts],
            model_name=self.model_name,
            dimension=8,
        )


class FallbackEmbeddingProvider(MockEmbeddingProvider):
    provider_name = "fallback"


class MockVectorStoreAdapter:
    """In-memory lifecycle stub matching the V1.1 adapter surface."""

    provider_name = "mock"

    def __init__(self) -> None:
        self.started = False
        self.closed = False
        self.start_config: Any = None
        self.lifecycle_events: list[str] = []
        self._items: dict[int, VectorItem] = {}

    def start(self, config: Any) -> ProviderHealth:
        self.lifecycle_events.append("vector.start")
        self.start_config = config
        self.started = True
        self.closed = False
        return self.health()

    def close(self) -> None:
        self.lifecycle_events.append("vector.close")
        self.closed = True
        self.started = False

    def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.provider_name,
            status="ok" if self.started else "stopped",
        )

    def ensure_collection(self, spec: Any) -> None:
        return None

    def upsert(self, items: list[Any]) -> UpsertResult:
        validated = [VectorItem.model_validate(item) for item in items]
        for item in validated:
            self._items[item.vector_pk] = item
        return UpsertResult(upserted=len(validated))

    def query(self, request: Any) -> list[VectorHit]:
        validated = VectorQuery.model_validate(request)
        hits = [
            VectorHit(
                vector_pk=item.vector_pk,
                memory_id=item.memory_id,
                user_id=item.user_id,
                status=item.status,
                score=_cosine_similarity(validated.vector, item.vector),
            )
            for item in self._items.values()
            if item.user_id == validated.user_id
            and item.status == validated.status
        ]
        hits.sort(key=lambda item: (-item.score, item.memory_id))
        return hits[: validated.top_k]

    def delete(self, vector_pks: list[int]) -> DeleteResult:
        deleted = 0
        missing: list[int] = []
        for vector_pk in dict.fromkeys(vector_pks):
            if self._items.pop(vector_pk, None) is None:
                missing.append(vector_pk)
            else:
                deleted += 1
        return DeleteResult(
            deleted=deleted,
            missing_vector_pks=missing,
        )


class FallbackVectorStoreAdapter(MockVectorStoreAdapter):
    provider_name = "fallback"


class MockIdempotencyRepository:
    def __init__(self) -> None:
        self.entries: dict[tuple[str, str, str], IdempotencyEntry] = {}

    def get(
        self, user_id: str, operation: str, idempotency_key: str
    ) -> IdempotencyEntry | None:
        return self.entries.get((user_id, operation, idempotency_key))

    def save(self, entry: IdempotencyEntry) -> None:
        self.entries[(entry.user_id, entry.operation, entry.idempotency_key)] = entry


class MockMemoryRepository:
    def __init__(self) -> None:
        self.records: dict[str, MemoryRecord] = {}
        self.vector_pks: dict[str, int] = {}

    def commit_ingest(self, result: Any) -> IngestCommitResult:
        records = list(result.knowledge.records)
        vector_items: list[VectorItem] = []
        for record in records:
            existing = self.records.get(record.memory_id)
            if existing is not None and existing.user_id != record.user_id:
                raise ValueError("memory_id already belongs to another user")
            self.records[record.memory_id] = record
            vector_pk = self.vector_pks.setdefault(
                record.memory_id,
                _mock_vector_pk(record.memory_id),
            )
            vector = record.attributes.get("embedding")
            if isinstance(vector, list) and vector:
                vector_items.append(
                    VectorItem(
                        vector_pk=vector_pk,
                        memory_id=record.memory_id,
                        user_id=record.user_id,
                        status=record.status,
                        vector=vector,
                    )
                )
        return IngestCommitResult(
            records=records,
            vector_items=vector_items,
        )

    def get_by_ids(
        self,
        user_id: str,
        memory_ids: list[str],
        statuses: list[MemoryStatus] | None = None,
    ) -> list[MemoryRecord]:
        allowed = set(statuses) if statuses is not None else None
        return [
            record
            for memory_id in memory_ids
            if (record := self.records.get(memory_id)) is not None
            and record.user_id == user_id
            and (allowed is None or record.status in allowed)
        ]

    def logical_delete(self, plan: ForgetExecutionPlan) -> LogicalDeleteResult:
        for memory_id in plan.memory_ids:
            record = self.records.get(memory_id)
            if record is not None and record.user_id != plan.user_id:
                raise ValueError("memory record does not belong to user")
            if record is not None:
                self.records[memory_id] = record.model_copy(
                    update={
                        "status": MemoryStatus.TOMBSTONED,
                        "revision": record.revision + 1,
                        "valid_to": datetime.now(timezone.utc),
                    }
                )
        return LogicalDeleteResult(
            plan_id=plan.plan_id,
            user_id=plan.user_id,
            memory_ids=plan.memory_ids,
            vector_pks=[
                self.vector_pks.setdefault(
                    memory_id,
                    _mock_vector_pk(memory_id),
                )
                for memory_id in plan.memory_ids
            ],
        )


class MockAuditRepository:
    def __init__(self) -> None:
        self.events: list[Any] = []

    def record(self, event: Any) -> AuditResult:
        self.events.append(event)
        return AuditResult(audit_id=f"audit_{len(self.events)}")


class MockEvaluationService:
    def run(self, request: Any) -> EvaluationRun:
        return EvaluationRun(
            run_id="run_mock",
            request_id=request.request_id,
            status="completed",
            metrics={name: 0.0 for name in request.metric_names},
            created_at=datetime.now(timezone.utc),
        )


def _memory_from_event(event: Envelope) -> MemoryRecord:
    content_text = _event_text(event)
    return MemoryRecord(
        memory_id=f"mem_{hashlib.blake2b(event.source_event_id.encode('utf-8'), digest_size=8).hexdigest()}",
        user_id=event.user_id,
        memory_kind="semantic",
        subtype="fact",
        content_text=content_text,
        content=dict(event.payload),
        status=MemoryStatus.ACTIVE,
        confidence=1.0,
        importance=0.5,
        revision=1,
        valid_from=event.occurred_at,
        scene_tags=[event.scene],
        source_refs=[event.source_event_id],
        supersedes=[],
        attributes={"embedding": _deterministic_vector(content_text)},
    )


def _event_text(event: Envelope) -> str:
    for key in ("content", "text", "result"):
        value = event.payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return json.dumps(
        event.payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _deterministic_vector(text: str) -> list[float]:
    vector = [0.0] * 8
    tokens = re.findall(r"\w+", text.casefold())
    if not tokens:
        vector[0] = 1.0
        return vector
    for token in tokens:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=2).digest()
        bucket = digest[0] % len(vector)
        vector[bucket] += 1.0 if digest[1] % 2 == 0 else -1.0
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [value / norm for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("mock vector dimension mismatch")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (
        left_norm * right_norm
    )


def _mock_vector_pk(memory_id: str) -> int:
    digest = hashlib.blake2b(
        memory_id.encode("utf-8"),
        digest_size=8,
        person=b"os-mock",
    ).digest()
    return int.from_bytes(digest, "big") & (2**63 - 1)


def _request_value(request: Any, key: str, default: Any) -> Any:
    if isinstance(request, Mapping):
        return request.get(key, default)
    return getattr(request, key, default)
