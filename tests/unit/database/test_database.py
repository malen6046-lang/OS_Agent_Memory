from pathlib import Path
import sqlite3

import pytest
from pydantic import BaseModel
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.database import get_session, init_db
from app.models import (
    AuditLogModel,
    EvaluationRunModel,
    IdempotencyRecordModel,
    MemoryRecordModel,
)


EXPECTED_COLUMNS = {
    "memory_record": {
        "memory_id",
        "user_id",
        "memory_kind",
        "content_text",
        "status",
        "confidence",
        "revision",
        "created_at",
        "updated_at",
    },
    "audit_log": {
        "audit_id",
        "operation",
        "operator",
        "request_id",
        "created_at",
    },
    "idempotency_record": {
        "idempotency_key",
        "operation",
        "request_id",
        "created_at",
    },
    "evaluation_run": {
        "run_id",
        "metric_name",
        "value",
        "created_at",
    },
}


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'memory-test.db').as_posix()}"


def test_init_db_creates_required_tables_and_columns(sqlite_url):
    engine = init_db(sqlite_url)
    inspector = inspect(engine)

    assert set(inspector.get_table_names()) == set(EXPECTED_COLUMNS)
    for table_name, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = {
            column["name"] for column in inspector.get_columns(table_name)
        }
        assert expected_columns <= actual_columns

    engine.dispose()


def test_init_db_accepts_file_path_and_is_idempotent(tmp_path):
    database_path = tmp_path / "path-input.db"

    first_engine = init_db(database_path)
    second_engine = init_db(database_path)

    assert database_path.is_file()
    assert set(inspect(second_engine).get_table_names()) == set(EXPECTED_COLUMNS)
    first_engine.dispose()
    second_engine.dispose()


def test_get_session_persists_all_models(sqlite_url):
    engine = init_db(sqlite_url)

    with get_session() as session:
        session.add_all(
            [
                MemoryRecordModel(
                    memory_id="mem_1",
                    user_id="usr_1",
                    memory_kind="semantic",
                    content_text="Database initialization test.",
                    status="active",
                    confidence=0.9,
                    revision=1,
                ),
                AuditLogModel(
                    audit_id="audit_1",
                    operation="memory.create",
                    operator="system",
                    request_id="req_1",
                ),
                IdempotencyRecordModel(
                    idempotency_key="idem_1",
                    operation="memory.create",
                    request_id="req_1",
                ),
                EvaluationRunModel(
                    run_id="run_1",
                    metric_name="precision",
                    value=0.95,
                ),
            ]
        )
        session.commit()

    with get_session() as session:
        memory = session.scalar(
            select(MemoryRecordModel).where(
                MemoryRecordModel.memory_id == "mem_1"
            )
        )
        assert memory is not None
        assert memory.created_at is not None
        assert memory.updated_at is not None
        assert session.get(AuditLogModel, "audit_1") is not None
        assert session.get(IdempotencyRecordModel, "idem_1") is not None
        assert session.get(EvaluationRunModel, "run_1") is not None

    engine.dispose()


@pytest.mark.parametrize(
    ("confidence", "revision"),
    [(-0.01, 1), (1.01, 1), (0.5, 0)],
)
def test_memory_database_constraints_reject_invalid_values(
    sqlite_url, confidence, revision
):
    engine = init_db(sqlite_url)

    with get_session() as session:
        session.add(
            MemoryRecordModel(
                memory_id=f"mem_{confidence}_{revision}",
                user_id="usr_1",
                memory_kind="semantic",
                content_text="Invalid record.",
                status="active",
                confidence=confidence,
                revision=revision,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    engine.dispose()


def test_orm_models_are_separate_from_pydantic_schemas():
    for model in (
        MemoryRecordModel,
        AuditLogModel,
        IdempotencyRecordModel,
        EvaluationRunModel,
    ):
        assert not issubclass(model, BaseModel)


def test_init_db_rejects_non_sqlite_url():
    with pytest.raises(ValueError, match="only SQLite"):
        init_db("postgresql://localhost/memory")


def test_init_db_migrates_legacy_memory_table_without_data_loss(tmp_path):
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE memory_record (
                memory_id VARCHAR PRIMARY KEY NOT NULL,
                user_id VARCHAR NOT NULL,
                memory_kind VARCHAR NOT NULL,
                content_text TEXT NOT NULL,
                status VARCHAR NOT NULL,
                confidence FLOAT NOT NULL,
                revision INTEGER NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO memory_record VALUES (
                'mem_legacy', 'usr_1', 'semantic', 'legacy', 'active',
                0.8, 1, '2026-08-03T00:00:00+00:00',
                '2026-08-03T00:00:00+00:00'
            )
            """
        )

    engine = init_db(database_path)
    columns = {
        column["name"] for column in inspect(engine).get_columns("memory_record")
    }

    assert {"vector_pk", "record_json"} <= columns
    with get_session() as session:
        row = session.get(MemoryRecordModel, "mem_legacy")
        assert row is not None
        assert row.content_text == "legacy"

    engine.dispose()
