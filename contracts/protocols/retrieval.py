"""Hybrid retrieval Protocol frozen by CR-20260803-001."""

from typing import Protocol

from contracts.schemas.retrieval import SearchRequest, SearchResponse


class HybridRetriever(Protocol):
    def search(self, request: SearchRequest) -> SearchResponse: ...
