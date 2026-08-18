"""Direct exports of the approved V1.2.2 contract Protocols."""

from contracts.protocols.embedding import EmbeddingProvider
from contracts.protocols.evaluation import EvaluationService
from contracts.protocols.forget import ForgetService
from contracts.protocols.knowledge import KnowledgeService
from contracts.protocols.memory import (
    AuditRepository,
    IdempotencyRepository,
    MemoryRepository,
)
from contracts.protocols.preference import PreferenceService
from contracts.protocols.retrieval import HybridRetriever
from contracts.protocols.safety import SafetyService
from contracts.protocols.vector_store import VectorStoreAdapter


# Backward-compatible name used by the existing dependency container.
Retriever = HybridRetriever

__all__ = [
    "AuditRepository",
    "EmbeddingProvider",
    "EvaluationService",
    "ForgetService",
    "HybridRetriever",
    "IdempotencyRepository",
    "KnowledgeService",
    "MemoryRepository",
    "PreferenceService",
    "Retriever",
    "SafetyService",
    "VectorStoreAdapter",
]
