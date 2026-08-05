"""Contract adapters for the pinned Algorithm V1.1 knowledge module."""

from .knowledge import KnowledgeServiceAdapter, build_knowledge_service
from .retrieval import HybridRetrieverAdapter, build_hybrid_retriever

__all__ = [
    "HybridRetrieverAdapter",
    "KnowledgeServiceAdapter",
    "build_hybrid_retriever",
    "build_knowledge_service",
]
