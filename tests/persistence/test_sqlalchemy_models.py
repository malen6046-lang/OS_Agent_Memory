from datetime import datetime, timezone

import pytest
from sqlalchemy import func, inspect, select

from app.core.database import (
    SqlAlchemyUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
)
from app.models import (
    Base,
    ForgetAuditModel,
    MemoryModel,
    MemoryTransitionModel,
    PreferenceModel,
    VectorMappingModel,
)
from app.repositories.sqlalchemy import (
    ForgetAuditSqlAlchemyRepository,
    KnowledgeSqlAlchemyRepository,
    MemorySqlAlchemyRepository,
    MemoryTransitionSqlAlchemyRepository,
    PreferenceSqlAlchemyRepository,
)
from contracts.schemas import (
    ForgetExecuteRequest,
    KnowledgeCreate,
    MemoryCreate,
    MemoryKind,
    MemoryStatus,
    PreferenceCreate,
    PreferenceUpdate,
)


@pytest.fixture
def database():
    engine = create_sqlite_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    try:
        yield engine, create_session_factory(engine)
    finally:
        engine.dispose()


def memory_create(
    *,
    user_id: str = "usr_test",
    memory_kind: str = "semantic",
    subtype: str = "fact",
    content_text: str = "测试记忆",
) -> MemoryCreate:
    return MemoryCreate(
        user_id=user_id,
        memory_kind=memory_kind,
        subtype=subtype,
        content_text=content_text,
        content={"text": content_text},
        confidence=0.8,
        importance=0.7,
        valid_from=datetime.now(timezone.utc),
        valid_to=None,
        expires_at=None,
        scene_tags=["office_automation"],
        source_refs=["evt_test"],
        supersedes=[],
        attributes={},
    )


def test_all_required_tables_and_indexes_exist(database):
    engine, _ = database
    inspector = inspect(engine)
    expected_tables = {
        "memories",
        "preferences",
        "preference_versions",
        "knowledge",
        "knowledge_versions",
        "knowledge_relations",
        "conflicts",
        "forget_audits",
        "memory_transitions",
        "evaluation_runs",
        "idempotency_records",
        "audit_logs",
        "vector_mappings",
    }
    assert set(inspector.get_table_names()) == expected_tables

    memory_indexes = {item["name"] for item in inspector.get_indexes("memories")}
    assert {
        "ix_memories_user_id",
        "ix_memories_memory_type",
        "ix_memories_status",
        "ix_memories_updated_at",
    }.issubset(memory_indexes)


def test_memory_repository_round_trip_preserves_timezone(database):
    _, session_factory = database
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        created = MemorySqlAlchemyRepository(uow.session).create(memory_create())
        memory_id = created.memory_id

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        loaded = MemorySqlAlchemyRepository(uow.session).get("usr_test", memory_id)
        assert loaded is not None
        assert loaded.valid_from.tzinfo is not None
        assert loaded.content_text == "测试记忆"


def test_unit_of_work_rolls_back_all_writes_on_exception(database):
    _, session_factory = database
    with pytest.raises(RuntimeError):
        with SqlAlchemyUnitOfWork(session_factory) as uow:
            assert uow.session is not None
            MemorySqlAlchemyRepository(uow.session).create(memory_create())
            raise RuntimeError("force rollback")

    with session_factory() as session:
        count = session.scalar(select(func.count()).select_from(MemoryModel))
        assert count == 0


def test_preference_repository_retains_history(database):
    _, session_factory = database
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        memory = MemorySqlAlchemyRepository(uow.session).create(
            memory_create(
                memory_kind="preference",
                subtype="output_style",
                content_text="用户喜欢表格输出",
            )
        )
        repository = PreferenceSqlAlchemyRepository(uow.session)
        current = repository.create(
            memory.memory_id,
            PreferenceCreate(
                user_id="usr_test",
                preference_key="output.format",
                value="table",
                category="output_style",
                scope="global",
                scope_value=None,
                polarity="positive",
                confidence=0.8,
                evidence=[{"source_event_id": "evt_1", "weight": 0.8}],
            ),
        )
        preference_id = uow.session.scalar(select(PreferenceModel.preference_id))
        assert preference_id is not None
        updated = repository.update(
            preference_id,
            PreferenceUpdate(
                value="markdown_table",
                confidence=0.9,
                evidence=[{"source_event_id": "evt_2", "weight": 0.9}],
                expected_revision=current.revision,
            ),
        )
        assert updated.revision == 2
        assert [item.revision for item in repository.history(preference_id)] == [1, 2]


def test_knowledge_repository_retains_history(database):
    _, session_factory = database
    first = KnowledgeCreate(
        title="终端打开方式",
        knowledge_type="workflow",
        body="打开应用菜单",
        steps=["打开菜单"],
        keywords=["终端"],
        source_uri=None,
        source_reliability=0.8,
        effective_at=datetime.now(timezone.utc),
    )
    second = first.model_copy(update={"body": "使用快捷键打开终端"})

    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        memory = MemorySqlAlchemyRepository(uow.session).create(memory_create())
        repository = KnowledgeSqlAlchemyRepository(uow.session)
        current = repository.create(memory.memory_id, "usr_test", first)
        repository.add_version(current.knowledge_id, 1, second)
        history = repository.history(current.knowledge_id)
        assert [item.revision for item in history] == [1, 2]
        assert history[0].body == "打开应用菜单"
        assert history[1].body == "使用快捷键打开终端"


def test_forget_operation_tombstones_and_writes_audit(database):
    _, session_factory = database
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        memory = MemorySqlAlchemyRepository(uow.session).create(memory_create())
        memory_id = memory.memory_id

    request = ForgetExecuteRequest(
        request_id="req_forget",
        idempotency_key="idem_forget",
        user_id="usr_test",
        source_event_id="evt_forget",
        confirmation_token="confirm_test",
        selected_ids=[memory_id],
    )
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        result = ForgetAuditSqlAlchemyRepository(
            uow.session
        ).finalize_tombstone_with_audit(request, plan_id="plan_test")
        assert result.tombstoned_ids == [memory_id]

    with session_factory() as session:
        stored_memory = session.get(MemoryModel, memory_id)
        audit = session.get(ForgetAuditModel, result.audit_id)
        assert stored_memory is not None
        assert stored_memory.status is MemoryStatus.TOMBSTONED
        assert audit is not None
        assert audit.requested_ids == [memory_id]
        assert audit.tombstoned_ids == [memory_id]


def test_memory_transition_is_recorded(database):
    _, session_factory = database
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        assert uow.session is not None
        memory = MemorySqlAlchemyRepository(uow.session).create(memory_create())
        transition_id = MemoryTransitionSqlAlchemyRepository(uow.session).record(
            memory_id=memory.memory_id,
            user_id="usr_test",
            from_memory_type=MemoryKind.EPISODIC,
            to_memory_type=MemoryKind.SEMANTIC,
            from_status=MemoryStatus.ACTIVE,
            to_status=MemoryStatus.ACTIVE,
            reason="跨会话重复验证",
            source_event_id="evt_transition",
        )

    with session_factory() as session:
        transition = session.get(MemoryTransitionModel, transition_id)
        assert transition is not None
        assert transition.to_memory_type is MemoryKind.SEMANTIC


def test_vector_mapping_has_no_vector_json_column(database):
    engine, _ = database
    columns = {item["name"] for item in inspect(engine).get_columns("vector_mappings")}
    assert {
        "memory_id",
        "vector_pk",
        "collection_name",
        "model_fingerprint",
        "dimension",
    }.issubset(columns)
    assert "vector" not in columns

    knowledge_columns = {
        item["name"] for item in inspect(engine).get_columns("knowledge_versions")
    }
    assert "vector" not in knowledge_columns
    assert "embedding" not in knowledge_columns
