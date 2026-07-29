"""Service ports anchored to the corresponding contracts.protocols modules."""

from __future__ import annotations

from typing import Any, Protocol

from contracts.protocols import forget as forget_contract
from contracts.protocols import knowledge as knowledge_contract
from contracts.protocols import preference as preference_contract
from contracts.protocols import retrieval as retrieval_contract


class PreferenceServicePort(Protocol):
    async def extract(self, event: Any) -> Any: ...


class KnowledgeServicePort(Protocol):
    async def ingest(self, event: Any, preference_result: Any) -> Any: ...


class RetrieverPort(Protocol):
    async def search(self, request: Any) -> Any: ...


class ForgetServicePort(Protocol):
    async def preview(self, request: Any) -> Any: ...

    async def execute(self, request: Any) -> Any: ...


# The contract modules are the authority. The fallback ports keep this layer
# usable while the currently empty protocol files are populated independently.
PreferenceService = getattr(
    preference_contract, "PreferenceService", PreferenceServicePort
)
KnowledgeService = getattr(
    knowledge_contract, "KnowledgeService", KnowledgeServicePort
)
Retriever = getattr(retrieval_contract, "HybridRetriever", RetrieverPort)
ForgetService = getattr(forget_contract, "ForgetService", ForgetServicePort)
