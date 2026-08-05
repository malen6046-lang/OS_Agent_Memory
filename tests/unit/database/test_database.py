"""Database initialization tests for the single V1.2.1 ORM model set."""

from pathlib import Path

import pytest
from sqlalchemy import inspect

from app.core.database import get_session, init_db


REQUIRED_TABLES = {
    "memory_record",
    "preference_current",
    "preference_versions",
    "knowledge",
    "knowledge_versions",
    "knowledge_relations",
    "conflict",
    "forget_audits",
    "memory_transitions",
    "evaluation_run",
    "idempotency_record",
    "audit_log",
    "vector_mappings",
}


@pytest.fixture
def sqlite_url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'memory-test.db').as_posix()}"


def test_init_db_creates_the_unified_model_set(sqlite_url):
    engine = init_db(sqlite_url)
    assert REQUIRED_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_init_db_accepts_file_path_and_get_session(tmp_path):
    database_path = tmp_path / "path-input.db"
    engine = init_db(database_path)
    with get_session() as session:
        assert session.bind is engine
    assert database_path.is_file()
    engine.dispose()


def test_init_db_rejects_non_sqlite_url():
    with pytest.raises(ValueError, match="only SQLite"):
        init_db("postgresql://localhost/memory")
