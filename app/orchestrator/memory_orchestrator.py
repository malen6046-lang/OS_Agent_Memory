"""Memory workflow coordination without business algorithms."""

from __future__ import annotations

from typing import Any

from .ports import (
    ForgetService,
    KnowledgeService,
    PreferenceService,
    Retriever,
)


class MemoryOrchestrator:
    """Delegate memory workflows to injected contract services."""

    def __init__(
        self,
        preference_service: PreferenceService,
        knowledge_service: KnowledgeService,
        retriever: Retriever,
        forget_service: ForgetService,
    ) -> None:
        self._preference_service = preference_service
        self._knowledge_service = knowledge_service
        self._retriever = retriever
        self._forget_service = forget_service

    async def ingest_event(self, event: Any) -> dict[str, Any]:
        preference_result = await self._preference_service.extract(event)
        knowledge_result = await self._knowledge_service.ingest(
            event, preference_result
        )
        return {
            "preference_result": preference_result,
            "knowledge_result": knowledge_result,
        }

    async def search_memory(self, request: Any) -> Any:
        return await self._retriever.search(request)

    async def ingest_knowledge(self, request: Any) -> Any:
        return await self._knowledge_service.ingest(request)

    async def preview_forget(self, request: Any) -> Any:
        return await self._forget_service.preview(request)

    async def execute_forget(self, request: Any) -> Any:
        return await self._forget_service.execute(request)
