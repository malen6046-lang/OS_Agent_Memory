"""Backend domain projection models that complement the four core tables.

These models intentionally reuse the existing ``memory_record``, ``audit_log``,
``idempotency_record``, and ``evaluation_run`` mappings instead of redefining
them. Contract enums are stored as strings so persistence stays behind the
frozen Pydantic boundary and can accept additive contract values.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, UTCDateTime, utc_now


class PreferenceModel(TimestampMixin, Base):
    """Current materialized value for one scoped preference."""

    __tablename__ = "preference_current"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_preference_current_confidence",
        ),
        CheckConstraint(
            "evidence_count >= 0",
            name="ck_preference_current_evidence_count",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_preference_current_revision",
        ),
        CheckConstraint(
            "length(trim(scope_value)) > 0",
            name="ck_preference_current_scope_value",
        ),
        UniqueConstraint(
            "memory_id",
            name="uq_preference_current_memory_id",
        ),
        UniqueConstraint(
            "user_id",
            "preference_key",
            "scope",
            "scope_value",
            name="uq_preference_current_scope",
        ),
        Index("ix_preference_current_user_id", "user_id"),
        Index("ix_preference_current_status", "status"),
        Index("ix_preference_current_updated_at", "updated_at"),
    )

    preference_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_record.memory_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    preference_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(128), nullable=False)
    polarity: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class PreferenceVersionModel(Base):
    """Immutable revision history for a current preference."""

    __tablename__ = "preference_versions"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_preference_versions_confidence",
        ),
        CheckConstraint(
            "evidence_count >= 0",
            name="ck_preference_versions_evidence_count",
        ),
        CheckConstraint(
            "revision >= 1",
            name="ck_preference_versions_revision",
        ),
        CheckConstraint(
            "length(trim(scope_value)) > 0",
            name="ck_preference_versions_scope_value",
        ),
        UniqueConstraint(
            "preference_id",
            "revision",
            name="uq_preference_versions_preference_revision",
        ),
        Index("ix_preference_versions_user_id", "user_id"),
        Index("ix_preference_versions_recorded_at", "recorded_at"),
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preference_id: Mapped[str] = mapped_column(
        ForeignKey("preference_current.preference_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_value: Mapped[str] = mapped_column(String(128), nullable=False)
    polarity: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )


class KnowledgeModel(TimestampMixin, Base):
    """Current pointer and state for a versioned knowledge memory."""

    __tablename__ = "knowledge"
    __table_args__ = (
        CheckConstraint(
            "current_revision >= 1",
            name="ck_knowledge_current_revision",
        ),
        UniqueConstraint("memory_id", name="uq_knowledge_memory_id"),
        Index("ix_knowledge_user_id", "user_id"),
        Index("ix_knowledge_status", "status"),
        Index("ix_knowledge_updated_at", "updated_at"),
    )

    knowledge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_record.memory_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class KnowledgeVersionModel(Base):
    """Immutable content snapshot for one knowledge revision."""

    __tablename__ = "knowledge_versions"
    __table_args__ = (
        CheckConstraint(
            "revision >= 1",
            name="ck_knowledge_versions_revision",
        ),
        CheckConstraint(
            "source_reliability >= 0.0 AND source_reliability <= 1.0",
            name="ck_knowledge_versions_source_reliability",
        ),
        UniqueConstraint(
            "knowledge_id",
            "revision",
            name="uq_knowledge_versions_knowledge_revision",
        ),
        Index("ix_knowledge_versions_user_id", "user_id"),
        Index("ix_knowledge_versions_recorded_at", "recorded_at"),
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge.knowledge_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    knowledge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_reliability: Mapped[float] = mapped_column(Float, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )


class KnowledgeRelationModel(TimestampMixin, Base):
    """Typed relation between two memory records."""

    __tablename__ = "knowledge_relations"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_knowledge_relations_confidence",
        ),
        UniqueConstraint(
            "source_memory_id",
            "target_memory_id",
            "relation",
            name="uq_knowledge_relations_edge",
        ),
        Index("ix_knowledge_relations_user_id", "user_id"),
        Index("ix_knowledge_relations_updated_at", "updated_at"),
    )

    relation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_record.memory_id"),
        nullable=False,
    )
    target_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_record.memory_id"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class ConflictModel(TimestampMixin, Base):
    """Persisted conflict decision between an old and new memory."""

    __tablename__ = "conflict"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="ck_conflict_confidence",
        ),
        Index("ix_conflict_user_id", "user_id"),
        Index("ix_conflict_status", "status"),
        Index("ix_conflict_updated_at", "updated_at"),
    )

    conflict_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    old_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_record.memory_id"),
        nullable=False,
    )
    new_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_record.memory_id"),
        nullable=False,
    )
    relation: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)


class ForgetAuditModel(Base):
    """Detailed execution record for two-stage forgetting."""

    __tablename__ = "forget_audits"
    __table_args__ = (
        Index("ix_forget_audits_user_id", "user_id"),
        Index("ix_forget_audits_status", "status"),
        Index("ix_forget_audits_executed_at", "executed_at"),
    )

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    tombstoned_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    failed_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )


class MemoryTransitionModel(Base):
    """Audit trail for memory kind and lifecycle transitions."""

    __tablename__ = "memory_transitions"
    __table_args__ = (
        Index("ix_memory_transitions_user_id", "user_id"),
        Index("ix_memory_transitions_to_memory_kind", "to_memory_kind"),
        Index("ix_memory_transitions_to_status", "to_status"),
        Index("ix_memory_transitions_transitioned_at", "transitioned_at"),
    )

    transition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_record.memory_id"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_memory_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    to_memory_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    transitioned_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )


class VectorMappingModel(TimestampMixin, Base):
    """Stable link from a memory record to a provider-specific vector key."""

    __tablename__ = "vector_mappings"
    __table_args__ = (
        CheckConstraint(
            "vector_pk >= 0",
            name="ck_vector_mappings_vector_pk",
        ),
        CheckConstraint(
            "dimension > 0",
            name="ck_vector_mappings_dimension",
        ),
        UniqueConstraint("memory_id", name="uq_vector_mappings_memory_id"),
        UniqueConstraint(
            "collection_name",
            "vector_pk",
            name="uq_vector_mappings_collection_vector_pk",
        ),
        Index("ix_vector_mappings_user_id", "user_id"),
        Index("ix_vector_mappings_status", "status"),
        Index("ix_vector_mappings_updated_at", "updated_at"),
    )

    mapping_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memory_record.memory_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_pk: Mapped[int] = mapped_column(BigInteger, nullable=False)
    collection_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
