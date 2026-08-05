from __future__ import annotations

from typing import Any

from contracts.schemas import (
    Envelope,
    EvaluationResult,
    EvaluationRunRequest,
    KnowledgeIngestRequest,
    KnowledgeIngestResult,
    MemoryResponse,
    PreferenceResponse,
)


class InMemoryRepository:
    """仅供骨架和契约测试使用；生产实现必须由独立 repository 替换。"""

    def __init__(self) -> None:
        self._events: dict[str, Envelope] = {}
        self._memories: dict[str, MemoryResponse] = {}

    async def save_events(self, events: list[Envelope]) -> int:
        for event in events:
            self._events[f"{event.user_id}:{event.source_event_id}"] = event
        return len(events)

    async def save_knowledge(
        self, request: KnowledgeIngestRequest, result: KnowledgeIngestResult
    ) -> None:
        for item in result.items:
            if item.memory is not None:
                self._memories[item.memory.memory_id] = item.memory

    async def get_memory(
        self, user_id: str, memory_id: str
    ) -> MemoryResponse | None:
        memory = self._memories.get(memory_id)
        return memory if memory and memory.user_id == user_id else None

    async def list_preferences(
        self, user_id: str, scene: str, keys: list[str] | None = None
    ) -> list[PreferenceResponse]:
        return []

    async def preference_versions(
        self, user_id: str, preference_key: str
    ) -> list[PreferenceResponse]:
        return []

    async def list_transitions(
        self, user_id: str, memory_id: str | None = None
    ) -> list[dict[str, Any]]:
        return []

    async def record_audit(self, **kwargs: Any) -> str:
        return "audit_in_memory"

    async def create_evaluation(
        self, request: EvaluationRunRequest, result: EvaluationResult
    ) -> None:
        return None
