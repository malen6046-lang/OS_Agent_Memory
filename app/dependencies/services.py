"""Dependency-injection container for MemoryOrchestrator."""

from __future__ import annotations

from dataclasses import dataclass

from app.orchestrator import MemoryOrchestrator
from app.orchestrator.ports import (
    ForgetService,
    KnowledgeService,
    PreferenceService,
    Retriever,
)

from .mock_services import (
    MockForgetService,
    MockKnowledgeService,
    MockPreferenceService,
    MockRetriever,
)


@dataclass(frozen=True)
class ServiceContainer:
    preference_service: PreferenceService
    knowledge_service: KnowledgeService
    retriever: Retriever
    forget_service: ForgetService


def build_mock_container() -> ServiceContainer:
    return ServiceContainer(
        preference_service=MockPreferenceService(),
        knowledge_service=MockKnowledgeService(),
        retriever=MockRetriever(),
        forget_service=MockForgetService(),
    )


def get_memory_orchestrator(
    container: ServiceContainer | None = None,
) -> MemoryOrchestrator:
    services = container or build_mock_container()
    return MemoryOrchestrator(
        preference_service=services.preference_service,
        knowledge_service=services.knowledge_service,
        retriever=services.retriever,
        forget_service=services.forget_service,
    )
