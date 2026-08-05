"""Repository protocols owned by the backend persistence layer."""

from __future__ import annotations

from typing import Any, Protocol

from contracts.schemas import (
    Envelope,
    EvaluationResult,
    EvaluationRunRequest,
    KnowledgeIngestRequest,
    KnowledgeIngestResult,
    MemoryResponse,
    PreferenceResponse,
)


class MemoryRepository(Protocol):
    async def save_events(self, events: list[Envelope]) -> int: ...
    async def save_knowledge(
        self, request: KnowledgeIngestRequest, result: KnowledgeIngestResult
    ) -> None: ...
    async def get_memory(
        self, user_id: str, memory_id: str
    ) -> MemoryResponse | None: ...
    async def list_transitions(
        self, user_id: str, memory_id: str | None = None
    ) -> list[dict[str, Any]]: ...


class PreferenceRepository(Protocol):
    async def list_preferences(
        self, user_id: str, scene: str, keys: list[str] | None = None
    ) -> list[PreferenceResponse]: ...
    async def preference_versions(
        self, user_id: str, preference_key: str
    ) -> list[PreferenceResponse]: ...


class KnowledgeRepository(Protocol):
    async def save_knowledge(
        self, request: KnowledgeIngestRequest, result: KnowledgeIngestResult
    ) -> None: ...


class AuditRepository(Protocol):
    async def record_audit(
        self,
        *,
        request_id: str,
        user_id: str,
        operation: str,
        target_ids: list[str],
        details: dict[str, Any],
    ) -> str: ...


class EvaluationRepository(Protocol):
    async def create_evaluation(
        self, request: EvaluationRunRequest, result: EvaluationResult
    ) -> None: ...


class PlatformRepository(
    MemoryRepository,
    PreferenceRepository,
    KnowledgeRepository,
    AuditRepository,
    EvaluationRepository,
    Protocol,
):
    """Composite persistence port consumed by ``MemoryApiService``."""
