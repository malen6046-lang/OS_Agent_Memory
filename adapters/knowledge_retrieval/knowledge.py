"""Frozen KnowledgeService adapter for Algorithm V1.1 components."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from contracts.schemas.common import (
    MemoryKind,
    MemoryStatus,
    MemorySubtype,
)
from contracts.schemas.envelope import Envelope
from contracts.schemas.knowledge import ConflictDecision, IngestResult
from contracts.schemas.memory import MemoryRecord
from contracts.schemas.preference import PreferenceRecord
from modules.knowledge_retrieval.algorithm_v1_1.conflict_classifier import (
    ConflictClassifier,
)
from modules.knowledge_retrieval.algorithm_v1_1.knowledge_service import (
    KnowledgeService as LegacyKnowledgeService,
)

from .runtime import KnowledgeRetrievalRuntime


ALGORITHM_SOURCE = "Algorithm---V1.1@8c1e47d"


class KnowledgeServiceAdapter:
    """Map frozen DTOs to the donor's pure knowledge algorithms.

    The donor ``KnowledgeService.ingest`` writes vector and metadata stores
    before the backend repository transaction. It is intentionally not called.
    This adapter reuses the donor BM25 and conflict classifier while leaving
    persistence and vector upsert to the existing Orchestrator/Repository flow.
    """

    def __init__(
        self,
        embedding_provider: Any,
        vector_store: Any,
        config: Any = None,
        app_config: Any = None,
    ) -> None:
        del config, app_config
        self.runtime = KnowledgeRetrievalRuntime(
            embedding_provider,
            vector_store,
        )
        self._classifier = ConflictClassifier()
        self._legacy_conflict_applier = LegacyKnowledgeService(
            None,
            None,
            None,
        )
        self._records: dict[str, MemoryRecord] = {}

    def ingest(
        self,
        events: list[Envelope],
        preferences: list[PreferenceRecord],
    ) -> IngestResult:
        validated_events = [Envelope.model_validate(event) for event in events]
        validated_preferences = [
            PreferenceRecord.model_validate(item) for item in preferences
        ]
        records: list[MemoryRecord] = []
        with self.runtime.lock:
            for index, event in enumerate(validated_events):
                record = self._record_from_event(
                    event,
                    validated_preferences,
                    index,
                )
                self.runtime.bm25.index([_bm25_document(record)])
                self._records[record.memory_id] = record
                records.append(record)
        return IngestResult(records=records, conflicts=[])

    def classify_conflict(
        self,
        old: MemoryRecord,
        new: MemoryRecord,
    ) -> ConflictDecision:
        old = MemoryRecord.model_validate(old)
        new = MemoryRecord.model_validate(new)
        old_meta = old.model_dump(mode="python")
        new_meta = new.model_dump(mode="python")
        raw = self._classifier.classify(
            new.content_text,
            new_meta,
            [
                {
                    "score": 1.0,
                    "meta": old_meta,
                }
            ],
        )
        relation = str(raw.get("relation", "unrelated"))
        strategy = str(raw.get("strategy", "manual_review"))
        reasons = raw.get("reasons", raw.get("reason_codes", []))
        confidence = max(0.0, min(1.0, float(raw.get("confidence", 0.0))))
        decision = ConflictDecision(
            relation=relation,
            old_memory_id=old.memory_id,
            new_memory_id=new.memory_id,
            confidence=confidence,
            strategy=strategy,
            reason_codes=[str(reason) for reason in reasons],
        )
        with self.runtime.lock:
            self._records[old.memory_id] = old
            self._records[new.memory_id] = new
        return decision

    def apply_conflict(self, decision: ConflictDecision) -> MemoryRecord:
        decision = ConflictDecision.model_validate(decision)
        raw = self._legacy_conflict_applier.apply_conflict(
            decision.model_dump(mode="python")
        )
        selected_id = str(raw.get("memory_id", ""))
        with self.runtime.lock:
            selected = self._records.get(selected_id)
            if selected is None:
                raise ValueError(
                    "conflict records are unavailable in this adapter instance"
                )
            status = MemoryStatus(raw.get("status", selected.status.value))
            supersedes = list(selected.supersedes)
            for memory_id in raw.get("supersedes", []):
                if memory_id and memory_id not in supersedes:
                    supersedes.append(memory_id)
            updated = selected.model_copy(
                update={
                    "status": status,
                    "revision": max(
                        selected.revision,
                        int(raw.get("revision", selected.revision)),
                    ),
                    "supersedes": supersedes,
                }
            )
            self._records[updated.memory_id] = updated
            return updated.model_copy(deep=True)

    def _record_from_event(
        self,
        event: Envelope,
        preferences: list[PreferenceRecord],
        index: int,
    ) -> MemoryRecord:
        content_text = _event_text(event)
        encoded = self.runtime.embedding.encode([content_text])
        vectors = encoded.get("vectors", [])
        if len(vectors) != 1:
            raise ValueError("embedding provider did not return one vector")
        payload = dict(event.payload)
        subtype = _subtype(payload.get("knowledge_type", payload.get("subtype")))
        memory_kind = _memory_kind(payload.get("memory_kind"))
        confidence = _unit_float(
            payload.get("source_reliability", payload.get("confidence", 0.8)),
            0.8,
        )
        importance = _unit_float(payload.get("importance", 0.5), 0.5)
        memory_id = _memory_id(event, index)
        applicable_keys = sorted(
            {
                preference.preference_key
                for preference in preferences
                if preference.status == MemoryStatus.ACTIVE
            }
        )
        return MemoryRecord(
            memory_id=memory_id,
            user_id=event.user_id,
            memory_kind=memory_kind,
            subtype=subtype,
            content_text=content_text,
            content=payload,
            status=MemoryStatus.ACTIVE,
            confidence=confidence,
            importance=importance,
            revision=1,
            valid_from=event.occurred_at,
            scene_tags=[event.scene],
            source_refs=[event.source_event_id],
            supersedes=[],
            attributes={
                "embedding": vectors[0],
                "embedding_model": encoded.get("model_name", "unknown"),
                "algorithm_source": ALGORITHM_SOURCE,
                "preference_keys": applicable_keys,
            },
        )


def build_knowledge_service(
    embedding_provider: Any,
    vector_store: Any,
    config: Any = None,
    app_config: Any = None,
) -> KnowledgeServiceAdapter:
    return KnowledgeServiceAdapter(
        embedding_provider=embedding_provider,
        vector_store=vector_store,
        config=config,
        app_config=app_config,
    )


def _memory_id(event: Envelope, index: int) -> str:
    identity = (
        f"{event.user_id}\0{event.source_event_id}\0{index}".encode("utf-8")
    )
    digest = hashlib.blake2b(
        identity,
        digest_size=12,
        person=b"knowledge-v11",
    ).hexdigest()
    return f"mem_{digest}"


def _event_text(event: Envelope) -> str:
    payload = event.payload
    pieces: list[str] = []
    for key in ("title", "body", "content_text", "text", "content", "result"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            pieces.append(value.strip())
    if pieces:
        return " ".join(dict.fromkeys(pieces))
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _bm25_document(record: MemoryRecord) -> dict[str, Any]:
    return {
        "doc_id": record.memory_id,
        "text": record.content_text,
        "content_text": record.content_text,
        "user_id": record.user_id,
        "memory_kind": record.memory_kind.value,
        "status": record.status.value,
    }


def _subtype(value: Any) -> MemorySubtype:
    try:
        return MemorySubtype(value)
    except (TypeError, ValueError):
        return MemorySubtype.FACT


def _memory_kind(value: Any) -> MemoryKind:
    try:
        return MemoryKind(value)
    except (TypeError, ValueError):
        return MemoryKind.SEMANTIC


def _unit_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(0.0, min(1.0, number))
