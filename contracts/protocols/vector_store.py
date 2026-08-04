"""Vector-store adapter Protocol frozen by CR-20260803-001."""

from typing import Protocol

from contracts.schemas.provider import (
    CollectionSpec,
    DeleteResult,
    ProviderHealth,
    UpsertResult,
    VectorHit,
    VectorItem,
    VectorQuery,
    VectorStoreConfig,
)


class VectorStoreAdapter(Protocol):
    def start(self, config: VectorStoreConfig) -> ProviderHealth: ...

    def close(self) -> None: ...

    def ensure_collection(self, spec: CollectionSpec) -> None: ...

    def upsert(self, items: list[VectorItem]) -> UpsertResult: ...

    def query(self, request: VectorQuery) -> list[VectorHit]: ...

    def delete(self, vector_pks: list[int]) -> DeleteResult: ...
