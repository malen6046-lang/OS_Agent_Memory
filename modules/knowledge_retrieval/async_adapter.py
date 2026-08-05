"""异步适配器 — 将同步算法包装为 orchestrator 需要的 async 接口.

Usage (by platform lead in app/dependencies/services.py):
    from modules.knowledge_retrieval.async_adapter import (
        AsyncKnowledgeServiceAdapter, AsyncHybridRetrieverAdapter
    )
    async_ks = AsyncKnowledgeServiceAdapter(services["knowledge_service"])
    async_hr = AsyncHybridRetrieverAdapter(services["hybrid_retriever"])
"""
from __future__ import annotations

from typing import Any


def normalize_request(request: Any) -> dict:
    """Convert Pydantic object or dict to plain dict for sync algorithm."""
    if hasattr(request, "model_dump"):
        return request.model_dump()
    if hasattr(request, "dict"):
        return request.dict()
    if isinstance(request, dict) and "payload" in request:
        payload = request["payload"]
        if hasattr(payload, "model_dump"):
            return payload.model_dump()
        if isinstance(payload, dict):
            return payload
    return dict(request) if isinstance(request, dict) else request


class AsyncKnowledgeServiceAdapter:
    """Wrap KnowledgeService.ingest into async ingest(event, preference_result)."""

    def __init__(self, knowledge_service: Any):
        self._ks = knowledge_service

    async def ingest(self, event: Any, preference_result: Any = None) -> dict:
        records = _extract_records(event)
        return self._ks.ingest(records)


class AsyncHybridRetrieverAdapter:
    """Wrap HybridRetriever.search into async search(request)."""

    def __init__(self, hybrid_retriever: Any):
        self._hr = hybrid_retriever

    async def search(self, request: Any) -> dict:
        req = normalize_request(request)
        return self._hr.search(req)


def _extract_records(event: Any) -> list[dict]:
    """Extract knowledge draft records from an Envelope-like event."""
    event = normalize_request(event)
    payload = event.get("payload", event)
    if isinstance(payload, dict) and "records" in payload:
        records = payload["records"]
    elif isinstance(payload, dict) and "text" in payload:
        records = [payload]
    elif isinstance(payload, dict) and "title" in payload:
        records = [payload]
    else:
        records = [payload] if isinstance(payload, dict) else []

    base = {
        "user_id": event.get("user_id", ""),
        "scene": event.get("scene", ""),
        "source_event_id": event.get("source_event_id", event.get("request_id", "")),
    }
    out = []
    for r in records:
        rec = dict(r) if isinstance(r, dict) else {"text": str(r)}
        rec.setdefault("user_id", base["user_id"])
        rec.setdefault("scene", base["scene"])
        rec.setdefault("source_event_id", base["source_event_id"])
        out.append(rec)
    return out
