"""Frozen contract exports consumed by the orchestration layer.

The contract modules are the sole authority. ``Any`` is used only while a
planned protocol has not yet been published; no duplicate Protocol is defined
inside ``app/orchestrator``.
"""

from typing import Any

from contracts.protocols import embedding as embedding_contract
from contracts.protocols import forget as forget_contract
from contracts.protocols import knowledge as knowledge_contract
from contracts.protocols import preference as preference_contract
from contracts.protocols import retrieval as retrieval_contract
from contracts.protocols import safety as safety_contract
from contracts.protocols import vector_store as vector_store_contract


PreferenceService = getattr(
    preference_contract, "PreferenceService", Any
)
KnowledgeService = getattr(knowledge_contract, "KnowledgeService", Any)
HybridRetriever = getattr(retrieval_contract, "HybridRetriever", Any)
ForgetService = getattr(forget_contract, "ForgetService", Any)
SafetyService = getattr(safety_contract, "SafetyService", Any)
EmbeddingProvider = getattr(
    embedding_contract, "EmbeddingProvider", Any
)
VectorStoreAdapter = getattr(
    vector_store_contract, "VectorStoreAdapter", Any
)

# Backward-compatible name used by the existing dependency container.
Retriever = HybridRetriever
