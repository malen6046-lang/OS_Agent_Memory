"""Dependency assembly for application services."""

from .errors import ServiceLifecycleError, ServiceStartupError
from .mock_services import (
    FallbackEmbeddingProvider,
    FallbackVectorStoreAdapter,
    MockEmbeddingProvider,
    MockForgetService,
    MockKnowledgeService,
    MockPreferenceService,
    MockRetriever,
    MockSafetyService,
    MockVectorStoreAdapter,
)
from .services import (
    ServiceContainer,
    build_mock_container,
    build_service_container,
    get_memory_orchestrator,
)

__all__ = [
    "FallbackEmbeddingProvider",
    "FallbackVectorStoreAdapter",
    "MockEmbeddingProvider",
    "MockForgetService",
    "MockKnowledgeService",
    "MockPreferenceService",
    "MockRetriever",
    "MockSafetyService",
    "MockVectorStoreAdapter",
    "ServiceContainer",
    "ServiceLifecycleError",
    "ServiceStartupError",
    "build_mock_container",
    "build_service_container",
    "get_memory_orchestrator",
]
