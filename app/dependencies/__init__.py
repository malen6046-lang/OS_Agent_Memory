"""Dependency assembly for application services."""

from .api_service import OrchestratorApiService
from .errors import (
    OrchestratorResponseError,
    ServiceLifecycleError,
    ServiceStartupError,
)
from .mock_services import (
    FallbackEmbeddingProvider,
    FallbackVectorStoreAdapter,
    MockAuditRepository,
    MockEmbeddingProvider,
    MockEvaluationService,
    MockForgetService,
    MockIdempotencyRepository,
    MockKnowledgeService,
    MockMemoryRepository,
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
    "MockAuditRepository",
    "MockEmbeddingProvider",
    "MockEvaluationService",
    "MockForgetService",
    "MockIdempotencyRepository",
    "MockKnowledgeService",
    "MockMemoryRepository",
    "MockPreferenceService",
    "MockRetriever",
    "MockSafetyService",
    "MockVectorStoreAdapter",
    "OrchestratorApiService",
    "OrchestratorResponseError",
    "ServiceContainer",
    "ServiceLifecycleError",
    "ServiceStartupError",
    "build_mock_container",
    "build_service_container",
    "get_memory_orchestrator",
]
