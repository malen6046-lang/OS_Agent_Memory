from typing import Protocol

from contracts.schemas import (
    ConflictDecision,
    ConflictResult,
    EmbeddingBatch,
    EmbeddingModelInfo,
    Envelope,
    ForgetExecuteRequest,
    ForgetPlan,
    ForgetPreviewRequest,
    ForgetResult,
    IndexInfo,
    KnowledgeCreate,
    KnowledgeIngestResult,
    MemoryResponse,
    PreferenceCandidate,
    PreferenceResponse,
    ProviderHealth,
    SearchRequest,
    SearchResponse,
)


class PreferenceService(Protocol):
    async def extract(self, events: list[Envelope]) -> list[PreferenceCandidate]: ...
    async def upsert(
        self, candidates: list[PreferenceCandidate]
    ) -> list[PreferenceResponse]: ...
    async def resolve(
        self, user_id: str, scene: str, keys: list[str] | None = None
    ) -> list[PreferenceResponse]: ...
    async def history(
        self, user_id: str, preference_key: str
    ) -> list[PreferenceResponse]: ...


class KnowledgeService(Protocol):
    async def ingest(self, records: list[KnowledgeCreate]) -> KnowledgeIngestResult: ...
    async def classify_conflict(
        self, old: MemoryResponse, new: MemoryResponse
    ) -> ConflictDecision: ...
    async def apply_conflict(self, decision: ConflictDecision) -> MemoryResponse: ...


class HybridRetriever(Protocol):
    async def search(self, request: SearchRequest) -> SearchResponse: ...


class ForgetService(Protocol):
    async def preview(self, request: ForgetPreviewRequest) -> ForgetPlan: ...
    async def execute(self, request: ForgetExecuteRequest) -> ForgetResult: ...


class ConflictService(Protocol):
    async def resolve(
        self, conflict_id: str, decision: ConflictDecision
    ) -> ConflictResult: ...


class EmbeddingProvider(Protocol):
    async def start(self) -> ProviderHealth: ...
    async def close(self) -> None: ...
    async def health(self, deep: bool = False) -> ProviderHealth: ...
    async def model_info(self) -> EmbeddingModelInfo: ...
    async def encode(self, texts: list[str]) -> EmbeddingBatch: ...


class VectorStoreAdapter(Protocol):
    async def start(self) -> ProviderHealth: ...
    async def close(self) -> None: ...
    async def ensure_collection(self, spec: IndexInfo) -> None: ...
    async def upsert(self, items: list[MemoryResponse]) -> list[int]: ...
    async def query(self, request: SearchRequest) -> SearchResponse: ...
    async def delete(self, vector_pks: list[int]) -> list[int]: ...
