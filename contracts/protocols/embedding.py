"""Embedding provider Protocol frozen by CR-20260803-001."""

from typing import Protocol

from contracts.schemas.provider import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderHealth,
)


class EmbeddingProvider(Protocol):
    def start(self) -> ProviderHealth: ...

    def close(self) -> None: ...

    def health(self, deep: bool = False) -> ProviderHealth: ...

    def model_info(self) -> EmbeddingModelInfo: ...

    def encode(self, texts: list[str]) -> EmbeddingBatch: ...
