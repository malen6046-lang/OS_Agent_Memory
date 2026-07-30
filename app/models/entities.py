from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UTCDateTime, utc_now
from contracts.schemas import (
    ConflictRelation,
    ConflictStrategy,
    EvaluationStatus,
    HealthStatus,
    MemoryKind,
    MemoryStatus,
    MemorySubtype,
    PreferenceCategory,
    PreferencePolarity,
    PreferenceScope,
)


def enum_column(enum_class: type, length: int = 32) -> SAEnum:
    return SAEnum(
        enum_class,
        native_enum=False,
        values_callable=lambda values: [item.value for item in values],
        validate_strings=True,
        create_constraint=True,
        length=length,
    )


class MemoryModel(TimestampMixin, Base):
    __tablename__ = "memories"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="confidence_range",
        ),
        CheckConstraint(
            "importance >= 0.0 AND importance <= 1.0",
            name="importance_range",
        ),
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index("ix_memories_user_id", "user_id"),
        Index("ix_memories_memory_type", "memory_type"),
        Index("ix_memories_status", "status"),
        Index("ix_memories_updated_at", "updated_at"),
        Index("ix_memories_user_status", "user_id", "status"),
    )

    memory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    memory_type: Mapped[MemoryKind] = mapped_column(
        enum_column(MemoryKind), nullable=False
    )
    subtype: Mapped[MemorySubtype] = mapped_column(
        enum_column(MemorySubtype), nullable=False
    )
    content_text: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        enum_column(MemoryStatus), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    importance: Mapped[float] = mapped_column(Float, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    valid_to: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    scene_tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    supersedes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    preference: Mapped["PreferenceModel | None"] = relationship(
        back_populates="memory", uselist=False
    )
    knowledge: Mapped["KnowledgeModel | None"] = relationship(
        back_populates="memory", uselist=False
    )
    vector_mapping: Mapped["VectorMappingModel | None"] = relationship(
        back_populates="memory", uselist=False
    )


class PreferenceModel(TimestampMixin, Base):
    __tablename__ = "preferences"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="confidence_range",
        ),
        CheckConstraint("evidence_count >= 0", name="evidence_count_nonnegative"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        UniqueConstraint(
            "user_id", "preference_key", "scope", "scope_value",
            name="uq_preferences_scope",
        ),
        Index("ix_preferences_user_id", "user_id"),
        Index("ix_preferences_status", "status"),
        Index("ix_preferences_updated_at", "updated_at"),
    )

    preference_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.memory_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    preference_key: Mapped[str] = mapped_column(String(128), nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    category: Mapped[PreferenceCategory] = mapped_column(
        enum_column(PreferenceCategory), nullable=False
    )
    scope: Mapped[PreferenceScope] = mapped_column(
        enum_column(PreferenceScope), nullable=False
    )
    # global的Pydantic None在Repository内映射为数据库空字符串，保证唯一约束有效。
    scope_value: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    polarity: Mapped[PreferencePolarity] = mapped_column(
        enum_column(PreferencePolarity), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        enum_column(MemoryStatus), nullable=False
    )

    memory: Mapped[MemoryModel] = relationship(back_populates="preference")
    versions: Mapped[list["PreferenceVersionModel"]] = relationship(
        back_populates="preference",
        cascade="all, delete-orphan",
        order_by="PreferenceVersionModel.revision",
    )


class PreferenceVersionModel(Base):
    __tablename__ = "preference_versions"
    __table_args__ = (
        UniqueConstraint("preference_id", "revision"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        Index("ix_preference_versions_user_id", "user_id"),
        Index("ix_preference_versions_updated_at", "recorded_at"),
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preference_id: Mapped[str] = mapped_column(
        ForeignKey("preferences.preference_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    category: Mapped[PreferenceCategory] = mapped_column(
        enum_column(PreferenceCategory), nullable=False
    )
    scope: Mapped[PreferenceScope] = mapped_column(
        enum_column(PreferenceScope), nullable=False
    )
    scope_value: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    polarity: Mapped[PreferencePolarity] = mapped_column(
        enum_column(PreferencePolarity), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        enum_column(MemoryStatus), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )

    preference: Mapped[PreferenceModel] = relationship(back_populates="versions")


class KnowledgeModel(TimestampMixin, Base):
    __tablename__ = "knowledge"
    __table_args__ = (
        CheckConstraint("current_revision >= 1", name="revision_positive"),
        Index("ix_knowledge_user_id", "user_id"),
        Index("ix_knowledge_status", "status"),
        Index("ix_knowledge_updated_at", "updated_at"),
    )

    knowledge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.memory_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    current_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        enum_column(MemoryStatus), nullable=False
    )

    memory: Mapped[MemoryModel] = relationship(back_populates="knowledge")
    versions: Mapped[list["KnowledgeVersionModel"]] = relationship(
        back_populates="knowledge",
        cascade="all, delete-orphan",
        order_by="KnowledgeVersionModel.revision",
    )


class KnowledgeVersionModel(Base):
    __tablename__ = "knowledge_versions"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "revision"),
        CheckConstraint("revision >= 1", name="revision_positive"),
        CheckConstraint(
            "source_reliability >= 0.0 AND source_reliability <= 1.0",
            name="source_reliability_range",
        ),
        Index("ix_knowledge_versions_user_id", "user_id"),
        Index("ix_knowledge_versions_updated_at", "recorded_at"),
    )

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    knowledge_id: Mapped[str] = mapped_column(
        ForeignKey("knowledge.knowledge_id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    knowledge_type: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    steps: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_uri: Mapped[str | None] = mapped_column(Text)
    source_reliability: Mapped[float] = mapped_column(Float, nullable=False)
    effective_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )

    knowledge: Mapped[KnowledgeModel] = relationship(back_populates="versions")


class KnowledgeRelationModel(TimestampMixin, Base):
    __tablename__ = "knowledge_relations"
    __table_args__ = (
        UniqueConstraint("source_memory_id", "target_memory_id", "relation"),
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="confidence_range",
        ),
        Index("ix_knowledge_relations_user_id", "user_id"),
        Index("ix_knowledge_relations_updated_at", "updated_at"),
    )

    relation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.memory_id"), nullable=False
    )
    target_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.memory_id"), nullable=False
    )
    relation: Mapped[ConflictRelation] = mapped_column(
        enum_column(ConflictRelation), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)


class ConflictModel(TimestampMixin, Base):
    __tablename__ = "conflicts"
    __table_args__ = (
        CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="confidence_range",
        ),
        Index("ix_conflicts_user_id", "user_id"),
        Index("ix_conflicts_status", "status"),
        Index("ix_conflicts_updated_at", "updated_at"),
    )

    conflict_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    old_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.memory_id"), nullable=False
    )
    new_memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.memory_id"), nullable=False
    )
    relation: Mapped[ConflictRelation] = mapped_column(
        enum_column(ConflictRelation), nullable=False
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    strategy: Mapped[ConflictStrategy] = mapped_column(
        enum_column(ConflictStrategy), nullable=False
    )
    reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        enum_column(MemoryStatus), nullable=False
    )


class ForgetAuditModel(Base):
    __tablename__ = "forget_audits"
    __table_args__ = (
        Index("ix_forget_audits_user_id", "user_id"),
        Index("ix_forget_audits_status", "status"),
        Index("ix_forget_audits_updated_at", "executed_at"),
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
        UTCDateTime(), default=utc_now, nullable=False
    )


class MemoryTransitionModel(Base):
    __tablename__ = "memory_transitions"
    __table_args__ = (
        Index("ix_memory_transitions_user_id", "user_id"),
        Index("ix_memory_transitions_memory_type", "to_memory_type"),
        Index("ix_memory_transitions_status", "to_status"),
        Index("ix_memory_transitions_updated_at", "transitioned_at"),
    )

    transition_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.memory_id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_memory_type: Mapped[MemoryKind] = mapped_column(
        enum_column(MemoryKind), nullable=False
    )
    to_memory_type: Mapped[MemoryKind] = mapped_column(
        enum_column(MemoryKind), nullable=False
    )
    from_status: Mapped[MemoryStatus] = mapped_column(
        enum_column(MemoryStatus), nullable=False
    )
    to_status: Mapped[MemoryStatus] = mapped_column(
        enum_column(MemoryStatus), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    transitioned_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )


class EvaluationRunModel(TimestampMixin, Base):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("ix_evaluation_runs_user_id", "user_id"),
        Index("ix_evaluation_runs_status", "status"),
        Index("ix_evaluation_runs_updated_at", "updated_at"),
    )

    evaluation_run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(
        enum_column(EvaluationStatus), nullable=False
    )
    evaluation_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    report_uri: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (
        UniqueConstraint("user_id", "operation", "idempotency_key"),
        Index("ix_idempotency_records_user_id", "user_id"),
        Index("ix_idempotency_records_updated_at", "created_at"),
    )

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)


class AuditLogModel(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_user_id", "user_id"),
        Index("ix_audit_logs_updated_at", "created_at"),
    )

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    target_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utc_now, nullable=False
    )


class VectorMappingModel(TimestampMixin, Base):
    __tablename__ = "vector_mappings"
    __table_args__ = (
        UniqueConstraint("collection_name", "vector_pk"),
        Index("ix_vector_mappings_user_id", "user_id"),
        Index("ix_vector_mappings_status", "status"),
        Index("ix_vector_mappings_updated_at", "updated_at"),
    )

    mapping_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    memory_id: Mapped[str] = mapped_column(
        ForeignKey("memories.memory_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    vector_pk: Mapped[int] = mapped_column(BigInteger, nullable=False)
    collection_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_fingerprint: Mapped[str] = mapped_column(String(256), nullable=False)
    dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[HealthStatus] = mapped_column(
        enum_column(HealthStatus), nullable=False
    )

    memory: Mapped[MemoryModel] = relationship(back_populates="vector_mapping")
