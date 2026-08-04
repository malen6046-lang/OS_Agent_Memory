"""Cross-module workflows for OS Agent Memory.

This module coordinates injected contract implementations. It contains no
database, vendor SDK, FastAPI, repository implementation, or ranking logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import logging
from copy import deepcopy
from collections.abc import Mapping
from time import monotonic
from typing import Any

from contracts.schemas.common import MemoryStatus
from contracts.schemas.envelope import Envelope
from contracts.schemas.evaluation import EvaluationRun, EvaluationRunRequest
from contracts.schemas.forget import (
    ForgetExecuteRequest,
    ForgetExecutionPlan,
    ForgetPlan,
    ForgetPreviewRequest,
)
from contracts.schemas.knowledge import IngestResult
from contracts.schemas.persistence import (
    AuditEvent,
    AuditResult,
    IdempotencyEntry,
    IngestCommitResult,
    IngestServiceResult,
    LogicalDeleteResult,
)
from contracts.schemas.preference import PreferenceCandidate, PreferenceRecord
from contracts.schemas.provider import DeleteResult, UpsertResult
from contracts.schemas.responses import (
    ApiResponse,
    ErrorCode,
    ErrorDetail,
    ResponseMeta,
)
from contracts.schemas.retrieval import SearchRequest, SearchResponse
from contracts.schemas.safety import SafetyCheckResult

from .errors import (
    DependencyUnavailableError,
    IdempotencyConflictError,
    OrchestratorError,
    OrchestratorTimeoutError,
    SensitiveContentBlockedError,
    ValidationOrchestratorError,
)
from .ports import (
    AuditRepository,
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


DEFAULT_TIMEOUT_SECONDS = 0.5
ACTIVE_STATUS = MemoryStatus.ACTIVE.value


class MemoryOrchestrator:
    """The single cross-module coordinator for memory workflows."""

    def __init__(
        self,
        preference_service: PreferenceService,
        knowledge_service: KnowledgeService,
        retriever: HybridRetriever,
        forget_service: ForgetService,
        *,
        safety_service: SafetyService | None = None,
        idempotency_repository: IdempotencyRepository | None = None,
        repository: MemoryRepository | None = None,
        vector_store: VectorStoreAdapter | None = None,
        audit_repository: AuditRepository | None = None,
        evaluation_service: EvaluationService | None = None,
        fallback_retriever: HybridRetriever | None = None,
        timeout_seconds: float | Mapping[str, float] = (
            DEFAULT_TIMEOUT_SECONDS
        ),
        logger: logging.Logger | None = None,
    ) -> None:
        self._preference_service = preference_service
        self._knowledge_service = knowledge_service
        self._retriever = retriever
        self._forget_service = forget_service
        self._safety_service = safety_service
        self._idempotency_repository = idempotency_repository
        self._repository = repository
        self._vector_store = vector_store
        self._audit_repository = audit_repository
        self._evaluation_service = evaluation_service
        self._fallback_retriever = fallback_retriever
        self._timeouts = timeout_seconds
        self._logger = logger or logging.getLogger(__name__)

    async def ingest(self, envelope: Envelope | Mapping[str, Any]) -> dict[str, Any]:
        """Validate, deduplicate, check safety, persist, sync, and audit."""
        started = monotonic()
        request_id = _value(envelope, "request_id", "")
        self._log("ingest", "start", request_id)

        try:
            validated = self._validate_envelope(envelope)
            request_id = validated.request_id
            fingerprint = _envelope_fingerprint(validated)

            existing = await self._dependency_call(
                "idempotency_repository",
                self._idempotency_repository,
                "get",
                validated.user_id,
                "ingest",
                validated.idempotency_key,
            )
            if existing is not None:
                existing = _contract_result(
                    IdempotencyEntry,
                    existing,
                    "idempotency_repository",
                    "get",
                )
            self._log("ingest", "idempotency_checked", request_id)
            replay = self._replay_response(existing, fingerprint)
            if replay is not None:
                replay["request_id"] = request_id
                replay.setdefault("meta", {})["idempotent_replay"] = True
                self._log("ingest", "replayed", request_id)
                return replay

            safety_result = await self._dependency_call(
                "safety_service",
                self._safety_service,
                "check",
                validated,
            )
            safety_result = _contract_result(
                SafetyCheckResult,
                safety_result,
                "safety_service",
                "check",
            )
            if _is_safety_blocked(safety_result):
                raise SensitiveContentBlockedError()
            self._log("ingest", "safety_checked", request_id)

            candidates = await self._dependency_call(
                "preference_service",
                self._preference_service,
                "extract",
                [validated],
            )
            candidates = _contract_list(
                PreferenceCandidate,
                candidates,
                "preference_service",
                "extract",
            )
            preferences = await self._dependency_call(
                "preference_service",
                self._preference_service,
                "upsert",
                candidates,
            )
            preferences = _contract_list(
                PreferenceRecord,
                preferences,
                "preference_service",
                "upsert",
            )
            knowledge = await self._dependency_call(
                "knowledge_service",
                self._knowledge_service,
                "ingest",
                [validated],
                preferences,
            )
            knowledge = _contract_result(
                IngestResult,
                knowledge,
                "knowledge_service",
                "ingest",
            )
            service_result = IngestServiceResult(
                preferences=preferences,
                knowledge=knowledge,
            )
            self._log("ingest", "services_called", request_id)

            committed = await self._dependency_call(
                "repository",
                self._repository,
                "commit_ingest",
                service_result,
            )
            committed = _contract_result(
                IngestCommitResult,
                committed,
                "repository",
                "commit_ingest",
            )
            self._log("ingest", "repository_committed", request_id)

            vector_items = committed.vector_items
            vector_result = await self._dependency_call(
                "vector_store",
                self._vector_store,
                "upsert",
                vector_items,
            )
            vector_result = _contract_result(
                UpsertResult,
                vector_result,
                "vector_store",
                "upsert",
            )
            self._log("ingest", "vector_synced", request_id)

            audit_result = await self._write_audit(
                operation="memory.ingest",
                request_id=request_id,
                user_id=validated.user_id,
                metadata={
                    "source_event_id": validated.source_event_id,
                    "record_count": len(vector_items),
                },
            )
            data = {
                "preference_result": preferences,
                "knowledge_result": knowledge,
                "repository_result": committed,
                "vector_result": vector_result,
                "audit_result": audit_result,
            }
            response = self._success(
                request_id, data, started, provider="configured"
            )

            entry = IdempotencyEntry(
                user_id=validated.user_id,
                operation="ingest",
                idempotency_key=validated.idempotency_key,
                fingerprint=fingerprint,
                response=response,
            )
            await self._dependency_call(
                "idempotency_repository",
                self._idempotency_repository,
                "save",
                entry,
            )
            self._log("ingest", "completed", request_id)
            return response
        except OrchestratorError as exc:
            self._log("ingest", "failed", request_id, error_code=exc.code)
            return self._failure(request_id, exc, started)

    async def search(self, request: Any) -> dict[str, Any]:
        """Run hybrid retrieval and enforce user/status isolation."""
        started = monotonic()
        request_id = _value(request, "request_id", "")
        self._log("search", "start", request_id)

        try:
            validated_request = _request_contract(SearchRequest, request)
            user_id = validated_request.user_id
        except ValidationOrchestratorError as exc:
            return self._failure(request_id, exc, started)

        degraded = False
        provider = "hybrid"
        degradation_reason: str | None = None
        try:
            result = await self._dependency_call(
                "hybrid_retriever",
                self._retriever,
                "search",
                validated_request,
                timeout_code=ErrorCode.SEARCH_TIMEOUT,
            )
            result = _contract_result(
                SearchResponse,
                result,
                "hybrid_retriever",
                "search",
            )
        except (DependencyUnavailableError, OrchestratorTimeoutError) as exc:
            if self._fallback_retriever is None:
                self._log(
                    "search", "failed", request_id, error_code=exc.code
                )
                return self._failure(request_id, exc, started)
            try:
                result = await self._dependency_call(
                    "fallback_retriever",
                    self._fallback_retriever,
                    "search",
                    validated_request,
                    timeout_code=ErrorCode.SEARCH_TIMEOUT,
                )
                result = _contract_result(
                    SearchResponse,
                    result,
                    "fallback_retriever",
                    "search",
                )
            except OrchestratorError as fallback_error:
                self._log(
                    "search",
                    "failed",
                    request_id,
                    error_code=fallback_error.code,
                )
                return self._failure(request_id, fallback_error, started)
            degraded = True
            provider = "fallback"
            degradation_reason = exc.code
            self._log("search", "degraded", request_id, error_code=exc.code)

        filtered = _filter_search_result(result, user_id)
        self._log("search", "filtered", request_id)
        return self._success(
            request_id,
            filtered,
            started,
            degraded=degraded,
            provider=provider,
            degradation_reason=degradation_reason,
        )

    async def preview_forget(self, request: Any) -> dict[str, Any]:
        """Build a candidate plan and confirmation token without mutation."""
        if not _value(request, "request_id", None):
            return await self._legacy_call(
                "forget_service", self._forget_service, "preview", request
            )
        started = monotonic()
        request_id = _value(request, "request_id", "")
        self._log("forget.preview", "start", request_id)
        try:
            validated_request = _request_contract(
                ForgetPreviewRequest, request
            )
            plan = await self._dependency_call(
                "forget_service",
                self._forget_service,
                "preview",
                validated_request,
            )
            plan = _contract_result(
                ForgetPlan,
                plan,
                "forget_service",
                "preview",
            )
            self._log("forget.preview", "completed", request_id)
            return self._success(
                request_id, plan, started, provider="forget_service"
            )
        except OrchestratorError as exc:
            self._log(
                "forget.preview", "failed", request_id, error_code=exc.code
            )
            return self._failure(request_id, exc, started)

    async def execute_forget(self, request: Any) -> dict[str, Any]:
        """Logically delete, remove precise vectors, then write audit."""
        if not _value(request, "request_id", None):
            return await self._legacy_call(
                "forget_service", self._forget_service, "execute", request
            )
        started = monotonic()
        request_id = _value(request, "request_id", "")
        self._log("forget.execute", "start", request_id)
        try:
            validated_request = _request_contract(
                ForgetExecuteRequest, request
            )
            user_id = validated_request.user_id

            execution_plan = await self._dependency_call(
                "forget_service",
                self._forget_service,
                "execute",
                validated_request,
            )
            execution_plan = _contract_result(
                ForgetExecutionPlan,
                execution_plan,
                "forget_service",
                "execute",
            )
            logical_result = await self._dependency_call(
                "repository",
                self._repository,
                "logical_delete",
                execution_plan,
            )
            logical_result = _contract_result(
                LogicalDeleteResult,
                logical_result,
                "repository",
                "logical_delete",
            )
            self._log("forget.execute", "logical_delete", request_id)

            vector_pks = logical_result.vector_pks
            vector_result = await self._dependency_call(
                "vector_store",
                self._vector_store,
                "delete",
                vector_pks,
            )
            vector_result = _contract_result(
                DeleteResult,
                vector_result,
                "vector_store",
                "delete",
            )
            self._log("forget.execute", "vector_delete", request_id)

            memory_ids = logical_result.memory_ids
            audit_result = await self._write_audit(
                operation="memory.forget",
                request_id=request_id,
                user_id=user_id,
                metadata={
                    "memory_ids": memory_ids,
                    "deleted_count": len(memory_ids),
                    "vector_delete_count": len(vector_pks),
                },
            )
            data = {
                "forget_result": logical_result,
                "vector_result": vector_result,
                "audit_result": audit_result,
            }
            self._log("forget.execute", "completed", request_id)
            return self._success(
                request_id, data, started, provider="forget_service"
            )
        except OrchestratorError as exc:
            self._log(
                "forget.execute", "failed", request_id, error_code=exc.code
            )
            return self._failure(request_id, exc, started)

    async def run_evaluation(self, request: Any) -> dict[str, Any]:
        """Delegate evaluation execution and return the standard envelope."""
        started = monotonic()
        request_id = _value(request, "request_id", "")
        self._log("evaluation", "start", request_id)
        try:
            validated_request = _request_contract(
                EvaluationRunRequest, request
            )
            result = await self._dependency_call(
                "evaluation_service",
                self._evaluation_service,
                "run",
                validated_request,
            )
            result = _contract_result(
                EvaluationRun,
                result,
                "evaluation_service",
                "run",
            )
            self._log("evaluation", "completed", request_id)
            return self._success(
                request_id, result, started, provider="evaluation_service"
            )
        except OrchestratorError as exc:
            self._log(
                "evaluation", "failed", request_id, error_code=exc.code
            )
            return self._failure(request_id, exc, started)

    # Compatibility entry points retained for the existing API facade. New
    # V1.2.2 integrations should call ingest/search directly.
    async def ingest_event(self, event: Any) -> dict[str, Any]:
        preference_result = await self._legacy_call(
            "preference_service", self._preference_service, "extract", event
        )
        knowledge_result = await self._legacy_call(
            "knowledge_service",
            self._knowledge_service,
            "ingest",
            event,
            preference_result,
        )
        return {
            "preference_result": preference_result,
            "knowledge_result": knowledge_result,
        }

    async def search_memory(self, request: Any) -> Any:
        return await self._legacy_call(
            "hybrid_retriever", self._retriever, "search", request
        )

    async def _legacy_call(
        self,
        dependency_name: str,
        dependency: Any,
        method_name: str,
        *args: Any,
    ) -> Any:
        try:
            return await self._invoke(
                dependency_name, dependency, method_name, *args
            )
        except OrchestratorTimeoutError as exc:
            raise TimeoutError(exc.message) from exc
        except DependencyUnavailableError as exc:
            raise RuntimeError(exc.message) from exc

    def _validate_envelope(
        self, envelope: Envelope | Mapping[str, Any]
    ) -> Envelope:
        if isinstance(envelope, Envelope):
            return envelope
        try:
            return Envelope.model_validate(envelope)
        except Exception as exc:
            raise ValidationOrchestratorError() from exc

    def _replay_response(
        self, existing: Any, fingerprint: str
    ) -> dict[str, Any] | None:
        if existing is None:
            return None
        existing_fingerprint = _value(
            existing, "fingerprint", _value(existing, "payload_hash", None)
        )
        if existing_fingerprint and existing_fingerprint != fingerprint:
            raise IdempotencyConflictError()
        response = _value(existing, "response", existing)
        if isinstance(response, Mapping):
            return deepcopy(dict(response))
        raise IdempotencyConflictError()

    async def _write_audit(
        self,
        *,
        operation: str,
        request_id: str,
        user_id: str,
        metadata: dict[str, Any],
    ) -> Any:
        event = AuditEvent(
            operation=operation,
            request_id=request_id,
            user_id=user_id,
            metadata=metadata,
        )
        result = await self._dependency_call(
            "audit_repository",
            self._audit_repository,
            "record",
            event,
        )
        result = _contract_result(
            AuditResult,
            result,
            "audit_repository",
            "record",
        )
        self._log(operation, "audit_written", request_id)
        return result

    async def _dependency_call(
        self,
        dependency_name: str,
        dependency: Any,
        method_name: str,
        *args: Any,
        timeout_code: ErrorCode = ErrorCode.DEPENDENCY_UNAVAILABLE,
    ) -> Any:
        try:
            return await self._invoke(
                dependency_name,
                dependency,
                method_name,
                *args,
                timeout_code=timeout_code,
            )
        except OrchestratorError:
            raise
        except Exception as exc:
            raise DependencyUnavailableError(
                dependency_name, method_name
            ) from exc

    async def _invoke(
        self,
        dependency_name: str,
        dependency: Any,
        method_name: str,
        *args: Any,
        timeout_code: ErrorCode = ErrorCode.DEPENDENCY_UNAVAILABLE,
    ) -> Any:
        if dependency is None:
            raise DependencyUnavailableError(dependency_name, method_name)
        method = getattr(dependency, method_name, None)
        if method is None or not callable(method):
            raise DependencyUnavailableError(dependency_name, method_name)

        timeout = self._timeout_for(f"{dependency_name}.{method_name}")
        try:
            if inspect.iscoroutinefunction(method):
                awaitable = method(*args)
            else:
                awaitable = asyncio.to_thread(method, *args)
            result = await asyncio.wait_for(awaitable, timeout=timeout)
            if inspect.isawaitable(result):
                result = await asyncio.wait_for(result, timeout=timeout)
            return result
        except TimeoutError as exc:
            raise OrchestratorTimeoutError(
                dependency_name,
                method_name,
                code=timeout_code,
            ) from exc

    def _timeout_for(self, step: str) -> float:
        if isinstance(self._timeouts, Mapping):
            value = self._timeouts.get(
                step, self._timeouts.get("default", DEFAULT_TIMEOUT_SECONDS)
            )
        else:
            value = self._timeouts
        if not isinstance(value, (int, float)) or value <= 0:
            return DEFAULT_TIMEOUT_SECONDS
        return float(value)

    def _success(
        self,
        request_id: str,
        data: Any,
        started: float,
        *,
        degraded: bool = False,
        provider: str,
        degradation_reason: str | None = None,
    ) -> dict[str, Any]:
        response = ApiResponse[Any](
            success=True,
            request_id=request_id,
            data=data,
            meta=ResponseMeta(
                elapsed_ms=_elapsed_ms(started),
                degraded=degraded,
                provider=provider,
                degradation_reason=degradation_reason,
            ),
        )
        return response.model_dump(mode="json")

    def _failure(
        self,
        request_id: str,
        error: OrchestratorError,
        started: float,
    ) -> dict[str, Any]:
        response = ApiResponse[Any](
            success=False,
            request_id=request_id or "req_unknown",
            error=ErrorDetail(
                code=error.code,
                message=error.message,
                retryable=error.retryable,
                details=error.details,
            ),
            meta=ResponseMeta(
                elapsed_ms=_elapsed_ms(started),
                degraded=False,
            ),
        )
        return response.model_dump(mode="json")

    def _log(
        self,
        flow: str,
        step: str,
        request_id: str,
        *,
        error_code: ErrorCode | None = None,
    ) -> None:
        fields = {
            "flow": flow,
            "step": step,
            "request_id": request_id,
        }
        if error_code:
            fields["error_code"] = error_code
        self._logger.info("memory_orchestrator", extra=fields)


def _value(source: Any, key: str, default: Any = None) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _request_contract(model: Any, value: Any) -> Any:
    try:
        return model.model_validate(value)
    except Exception as exc:
        raise ValidationOrchestratorError() from exc


def _contract_result(
    model: Any,
    value: Any,
    dependency: str,
    operation: str,
) -> Any:
    try:
        return model.model_validate(value)
    except Exception as exc:
        raise DependencyUnavailableError(
            dependency, f"{operation}.invalid_response"
        ) from exc


def _contract_list(
    model: Any,
    values: Any,
    dependency: str,
    operation: str,
) -> list[Any]:
    if not isinstance(values, list):
        raise DependencyUnavailableError(
            dependency, f"{operation}.invalid_response"
        )
    return [
        _contract_result(model, value, dependency, operation)
        for value in values
    ]


def _envelope_fingerprint(envelope: Envelope) -> str:
    fingerprint_data = envelope.model_dump(mode="json")
    fingerprint_data.pop("request_id", None)
    canonical = json.dumps(
        fingerprint_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_safety_blocked(result: Any) -> bool:
    allowed = _value(result, "allowed", True)
    blocked = _value(result, "blocked", False)
    return allowed is False or blocked is True


def _filter_search_result(result: Any, user_id: str) -> dict[str, Any]:
    if isinstance(result, Mapping):
        output = dict(result)
    elif hasattr(result, "model_dump"):
        output = result.model_dump(mode="json")
    else:
        output = {"items": result if isinstance(result, list) else []}

    items = output.get("items", [])
    if not isinstance(items, list):
        items = []
    output["items"] = [
        item
        for item in items
        if _item_value(item, "user_id") == user_id
        and _status_value(_item_value(item, "status")) == ACTIVE_STATUS
    ]
    if "total" in output:
        output["total"] = len(output["items"])
    return output


def _item_value(item: Any, key: str) -> Any:
    value = _value(item, key, None)
    if value is not None:
        return value
    record = _value(item, "record", None)
    return _value(record, key, None)


def _status_value(status: Any) -> Any:
    return getattr(status, "value", status)


def _elapsed_ms(started: float) -> int:
    return max(0, round((monotonic() - started) * 1000))
