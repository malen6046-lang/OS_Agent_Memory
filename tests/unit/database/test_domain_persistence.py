from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.core.database import (
    SqlAlchemyUnitOfWork,
    create_session_factory,
    create_sqlite_engine,
)
from app.models import (
    Base,
    MemoryRecordModel,
    MemoryTransitionModel,
    PreferenceModel,
)


@pytest.fixture
def database(tmp_path: Path):
    engine = create_sqlite_engine(tmp_path / "domain-models.db")
    Base.metadata.create_all(engine)
    try:
        yield engine, create_session_factory(engine)
    finally:
        engine.dispose()


def _memory(memory_id: str) -> MemoryRecordModel:
    return MemoryRecordModel(
        memory_id=memory_id,
        user_id="usr_test",
        memory_kind="episodic",
        content_text="A transaction boundary test.",
        status="active",
        confidence=0.9,
        revision=1,
    )


def test_unit_of_work_rolls_back_all_writes_on_exception(database):
    _, session_factory = database

    with pytest.raises(RuntimeError, match="force rollback"):
        with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
            assert unit_of_work.session is not None
            unit_of_work.session.add(_memory("mem_rollback"))
            raise RuntimeError("force rollback")

    with session_factory() as session:
        count = session.scalar(
            select(func.count()).select_from(MemoryRecordModel)
        )
        assert count == 0


def test_file_engine_enables_sqlite_safety_pragmas(database):
    engine, _ = database

    with engine.connect() as connection:
        assert connection.scalar(text("PRAGMA foreign_keys")) == 1
        assert connection.scalar(text("PRAGMA busy_timeout")) == 5000
        assert connection.scalar(text("PRAGMA journal_mode")) == "wal"


def test_domain_timestamp_round_trip_is_aware_utc(database):
    _, session_factory = database
    transitioned_at = datetime(2026, 8, 5, 8, 30, tzinfo=timezone.utc)

    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        assert unit_of_work.session is not None
        unit_of_work.session.add(_memory("mem_transition"))
        unit_of_work.session.flush()
        unit_of_work.session.add(
            MemoryTransitionModel(
                transition_id="transition_1",
                memory_id="mem_transition",
                user_id="usr_test",
                from_memory_kind="episodic",
                to_memory_kind="semantic",
                from_status="active",
                to_status="active",
                reason="Repeated cross-session evidence.",
                source_event_id="event_1",
                transitioned_at=transitioned_at,
            )
        )

    with session_factory() as session:
        stored = session.get(MemoryTransitionModel, "transition_1")
        assert stored is not None
        assert stored.transitioned_at == transitioned_at
        assert stored.transitioned_at.tzinfo is timezone.utc


def test_preference_scope_value_follows_frozen_non_empty_contract(database):
    _, session_factory = database

    with pytest.raises(IntegrityError):
        with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
            assert unit_of_work.session is not None
            unit_of_work.session.add(_memory("mem_preference"))
            unit_of_work.session.flush()
            unit_of_work.session.add(
                PreferenceModel(
                    preference_id="pref_1",
                    memory_id="mem_preference",
                    user_id="usr_test",
                    preference_key="ui.theme",
                    value="dark",
                    category="ui",
                    scope="global",
                    scope_value=" ",
                    polarity="positive",
                    confidence=0.9,
                    evidence_count=1,
                    revision=1,
                    status="active",
                )
            )
