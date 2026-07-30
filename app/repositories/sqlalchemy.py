from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ForgetAuditModel,
    KnowledgeModel,
    KnowledgeVersionModel,
    MemoryModel,
    MemoryTransitionModel,
    PreferenceModel,
    PreferenceVersionModel,
    VectorMappingModel,
)
from contracts.schemas import (
    ErrorCode,
    Evidence,
    ForgetExecuteRequest,
    ForgetFailedItem,
    ForgetResult,
    KnowledgeCreate,
    MemoryCreate,
    MemoryKind,
    MemoryResponse,
    MemoryStatus,
    MemoryUpdate,
    PreferenceCreate,
    PreferenceResponse,
    PreferenceUpdate,
)


class RevisionConflictError(RuntimeError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


def _memory_response(model: MemoryModel) -> MemoryResponse:
    return MemoryResponse(
        memory_id=model.memory_id,
        user_id=model.user_id,
        memory_kind=model.memory_type,
        subtype=model.subtype,
        content_text=model.content_text,
        content=model.content,
        status=model.status,
        confidence=model.confidence,
        importance=model.importance,
        revision=model.revision,
        valid_from=model.valid_from,
        valid_to=model.valid_to,
        expires_at=model.expires_at,
        scene_tags=model.scene_tags,
        source_refs=model.source_refs,
        supersedes=model.supersedes,
        attributes=model.attributes,
    )


class MemorySqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, data: MemoryCreate) -> MemoryResponse:
        model = MemoryModel(
            memory_id=_new_id("mem"),
            user_id=data.user_id,
            memory_type=data.memory_kind,
            subtype=data.subtype,
            content_text=data.content_text,
            content=data.content,
            status=MemoryStatus.ACTIVE,
            confidence=data.confidence,
            importance=data.importance,
            revision=1,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            expires_at=data.expires_at,
            scene_tags=data.scene_tags,
            source_refs=data.source_refs,
            supersedes=data.supersedes,
            attributes=data.attributes,
        )
        self._session.add(model)
        self._session.flush()
        return _memory_response(model)

    def get(self, user_id: str, memory_id: str) -> MemoryResponse | None:
        model = self._session.scalar(
            select(MemoryModel).where(
                MemoryModel.user_id == user_id,
                MemoryModel.memory_id == memory_id,
            )
        )
        return _memory_response(model) if model else None

    def update(
        self, user_id: str, memory_id: str, data: MemoryUpdate
    ) -> MemoryResponse:
        model = self._session.scalar(
            select(MemoryModel).where(
                MemoryModel.user_id == user_id,
                MemoryModel.memory_id == memory_id,
            )
        )
        if model is None:
            raise KeyError(memory_id)
        if model.revision != data.expected_revision:
            raise RevisionConflictError(memory_id)
        for field, value in data.model_dump(
            exclude={"expected_revision"}, exclude_unset=True
        ).items():
            setattr(model, field, value)
        model.revision += 1
        self._session.flush()
        return _memory_response(model)


class PreferenceSqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self, memory_id: str, data: PreferenceCreate
    ) -> PreferenceResponse:
        preference_id = _new_id("pref")
        current = PreferenceModel(
            preference_id=preference_id,
            memory_id=memory_id,
            user_id=data.user_id,
            preference_key=data.preference_key,
            value=data.value,
            category=data.category,
            scope=data.scope,
            scope_value=data.scope_value or "",
            polarity=data.polarity,
            confidence=data.confidence,
            evidence_count=len(data.evidence),
            revision=1,
            status=MemoryStatus.ACTIVE,
        )
        version = PreferenceVersionModel(
            version_id=_new_id("prefv"),
            preference_id=preference_id,
            user_id=data.user_id,
            revision=1,
            value=data.value,
            category=data.category,
            scope=data.scope,
            scope_value=data.scope_value or "",
            polarity=data.polarity,
            confidence=data.confidence,
            evidence=[item.model_dump(mode="json") for item in data.evidence],
            evidence_count=len(data.evidence),
            status=MemoryStatus.ACTIVE,
        )
        self._session.add_all([current, version])
        self._session.flush()
        return self._to_response(current, version)

    def update(
        self, preference_id: str, data: PreferenceUpdate
    ) -> PreferenceResponse:
        current = self._session.get(PreferenceModel, preference_id)
        if current is None:
            raise KeyError(preference_id)
        if current.revision != data.expected_revision:
            raise RevisionConflictError(preference_id)
        previous = self._latest_version(preference_id)
        value = data.value if "value" in data.model_fields_set else current.value
        polarity = data.polarity or current.polarity
        confidence = (
            data.confidence
            if "confidence" in data.model_fields_set
            else current.confidence
        )
        evidence = (
            data.evidence
            if "evidence" in data.model_fields_set and data.evidence is not None
            else [Evidence.model_validate(item) for item in previous.evidence]
        )
        current.value = value
        current.polarity = polarity
        current.confidence = confidence
        current.evidence_count = len(evidence)
        current.revision += 1
        version = PreferenceVersionModel(
            version_id=_new_id("prefv"),
            preference_id=current.preference_id,
            user_id=current.user_id,
            revision=current.revision,
            value=value,
            category=current.category,
            scope=current.scope,
            scope_value=current.scope_value,
            polarity=polarity,
            confidence=confidence,
            evidence=[item.model_dump(mode="json") for item in evidence],
            evidence_count=len(evidence),
            status=current.status,
        )
        self._session.add(version)
        self._session.flush()
        return self._to_response(current, version)

    def history(self, preference_id: str) -> list[PreferenceVersionModel]:
        return list(
            self._session.scalars(
                select(PreferenceVersionModel)
                .where(PreferenceVersionModel.preference_id == preference_id)
                .order_by(PreferenceVersionModel.revision)
            )
        )

    def _latest_version(self, preference_id: str) -> PreferenceVersionModel:
        version = self._session.scalar(
            select(PreferenceVersionModel)
            .where(PreferenceVersionModel.preference_id == preference_id)
            .order_by(PreferenceVersionModel.revision.desc())
            .limit(1)
        )
        if version is None:
            raise RuntimeError("preference current row has no history")
        return version

    @staticmethod
    def _to_response(
        current: PreferenceModel, version: PreferenceVersionModel
    ) -> PreferenceResponse:
        return PreferenceResponse(
            user_id=current.user_id,
            preference_key=current.preference_key,
            value=current.value,
            category=current.category,
            scope=current.scope,
            scope_value=current.scope_value or None,
            polarity=current.polarity,
            confidence=current.confidence,
            evidence=version.evidence,
            evidence_count=current.evidence_count,
            revision=current.revision,
            status=current.status,
        )


class KnowledgeSqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self, memory_id: str, user_id: str, data: KnowledgeCreate
    ) -> KnowledgeModel:
        knowledge_id = _new_id("kn")
        current = KnowledgeModel(
            knowledge_id=knowledge_id,
            memory_id=memory_id,
            user_id=user_id,
            current_revision=1,
            status=MemoryStatus.ACTIVE,
        )
        version = self._new_version(knowledge_id, user_id, 1, data)
        self._session.add_all([current, version])
        self._session.flush()
        return current

    def add_version(
        self, knowledge_id: str, expected_revision: int, data: KnowledgeCreate
    ) -> KnowledgeVersionModel:
        current = self._session.get(KnowledgeModel, knowledge_id)
        if current is None:
            raise KeyError(knowledge_id)
        if current.current_revision != expected_revision:
            raise RevisionConflictError(knowledge_id)
        current.current_revision += 1
        version = self._new_version(
            current.knowledge_id,
            current.user_id,
            current.current_revision,
            data,
        )
        self._session.add(version)
        self._session.flush()
        return version

    def history(self, knowledge_id: str) -> list[KnowledgeVersionModel]:
        return list(
            self._session.scalars(
                select(KnowledgeVersionModel)
                .where(KnowledgeVersionModel.knowledge_id == knowledge_id)
                .order_by(KnowledgeVersionModel.revision)
            )
        )

    @staticmethod
    def _new_version(
        knowledge_id: str, user_id: str, revision: int, data: KnowledgeCreate
    ) -> KnowledgeVersionModel:
        return KnowledgeVersionModel(
            version_id=_new_id("knv"),
            knowledge_id=knowledge_id,
            user_id=user_id,
            revision=revision,
            title=data.title,
            knowledge_type=data.knowledge_type,
            body=data.body,
            steps=data.steps,
            keywords=data.keywords,
            source_uri=data.source_uri,
            source_reliability=data.source_reliability,
            effective_at=data.effective_at,
        )


class ForgetAuditSqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def finalize_tombstone_with_audit(
        self,
        request: ForgetExecuteRequest,
        *,
        plan_id: str,
        failed_items: list[ForgetFailedItem] | None = None,
    ) -> ForgetResult:
        failures = list(failed_items or [])
        failed_ids = {item.memory_id for item in failures}
        tombstoned: list[str] = []
        for memory_id in request.selected_ids:
            if memory_id in failed_ids:
                continue
            memory = self._session.scalar(
                select(MemoryModel).where(
                    MemoryModel.user_id == request.user_id,
                    MemoryModel.memory_id == memory_id,
                )
            )
            if memory is None:
                failures.append(
                    ForgetFailedItem(
                        memory_id=memory_id,
                        code=ErrorCode.UNAUTHORIZED_SCOPE,
                        message="记忆不存在或不属于当前用户",
                    )
                )
                continue
            memory.status = MemoryStatus.TOMBSTONED
            memory.revision += 1
            mapping = self._session.scalar(
                select(VectorMappingModel).where(
                    VectorMappingModel.memory_id == memory_id
                )
            )
            if mapping is not None:
                self._session.delete(mapping)
            tombstoned.append(memory_id)

        audit_id = _new_id("audit")
        status = "completed" if not failures else "partial_failure"
        audit = ForgetAuditModel(
            audit_id=audit_id,
            plan_id=plan_id,
            request_id=request.request_id,
            idempotency_key=request.idempotency_key,
            user_id=request.user_id,
            source_event_id=request.source_event_id,
            requested_ids=request.selected_ids,
            tombstoned_ids=tombstoned,
            failed_items=[item.model_dump(mode="json") for item in failures],
            status=status,
        )
        self._session.add(audit)
        self._session.flush()
        return ForgetResult(
            plan_id=plan_id,
            requested_ids=request.selected_ids,
            tombstoned_ids=tombstoned,
            failed_items=failures,
            audit_id=audit_id,
        )


class MemoryTransitionSqlAlchemyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        memory_id: str,
        user_id: str,
        from_memory_type: MemoryKind,
        to_memory_type: MemoryKind,
        from_status: MemoryStatus,
        to_status: MemoryStatus,
        reason: str,
        source_event_id: str,
    ) -> str:
        transition_id = _new_id("transition")
        self._session.add(
            MemoryTransitionModel(
                transition_id=transition_id,
                memory_id=memory_id,
                user_id=user_id,
                from_memory_type=from_memory_type,
                to_memory_type=to_memory_type,
                from_status=from_status,
                to_status=to_status,
                reason=reason,
                source_event_id=source_event_id,
            )
        )
        self._session.flush()
        return transition_id
