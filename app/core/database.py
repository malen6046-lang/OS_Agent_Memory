"""SQLite engine initialization and SQLAlchemy session creation."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock
from types import TracebackType
from typing import Self

from sqlalchemy import Engine, URL, create_engine, event, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

from .config import ConfigManager


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_initialization_lock = Lock()


def create_sqlite_engine(
    database_url: str | Path | URL,
    *,
    echo: bool = False,
) -> Engine:
    """Create a configured SQLite engine without mutating ORM metadata."""
    url = _coerce_sqlite_url(database_url)
    if not url.drivername.startswith("sqlite"):
        raise ValueError("only SQLite database URLs are supported")

    _ensure_database_directory(url)
    engine = create_engine(
        url,
        echo=echo,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )
    _configure_sqlite(
        engine,
        persistent=url.database not in {None, ":memory:"},
    )
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create the shared SQLAlchemy 2.x session factory configuration."""
    return sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


class SqlAlchemyUnitOfWork:
    """Commit a session on success and roll it back on every failure."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> Self:
        self.session = self._session_factory()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> bool:
        if self.session is None:  # pragma: no cover - defensive invariant
            raise RuntimeError("unit of work session was not initialized")

        try:
            if exc_type is None:
                try:
                    self.session.commit()
                except Exception:
                    self.session.rollback()
                    raise
            else:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None
        return False


def init_db(database_url: str | Path | URL | None = None) -> Engine:
    """Initialize a SQLite engine and create every registered ORM table."""
    global _engine, _session_factory

    with _initialization_lock:
        url = (
            _coerce_sqlite_url(database_url)
            if database_url is not None
            else _default_url()
        )
        engine = create_sqlite_engine(url)

        try:
            Base.metadata.create_all(engine)
            _migrate_legacy_schema(engine)
        except Exception:
            engine.dispose()
            raise

        previous_engine = _engine
        _engine = engine
        _session_factory = create_session_factory(engine)
        if previous_engine is not None:
            previous_engine.dispose()
        return engine


def get_session() -> Session:
    """Return a new SQLAlchemy session, initializing the database if needed."""
    if _session_factory is None:
        init_db()
    if _session_factory is None:  # pragma: no cover - defensive invariant
        raise RuntimeError("database session factory was not initialized")
    return _session_factory()


def _default_url() -> URL:
    manager = ConfigManager()
    config = manager.load()
    data_dir = config.storage.data_dir.expanduser()
    if not data_dir.is_absolute():
        data_dir = manager.config_dir.parent / data_dir
    database_path = (data_dir / config.storage.sqlite_file).resolve()
    return URL.create("sqlite", database=str(database_path))


def _coerce_sqlite_url(database_url: str | Path | URL) -> URL:
    if isinstance(database_url, URL):
        return database_url
    if isinstance(database_url, Path):
        return URL.create(
            "sqlite", database=str(database_url.expanduser().resolve())
        )
    if "://" not in database_url:
        return URL.create(
            "sqlite", database=str(Path(database_url).expanduser().resolve())
        )
    return make_url(database_url)


def _ensure_database_directory(url: URL) -> None:
    database = url.database
    if database is None or database == ":memory:":
        return
    Path(database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def _configure_sqlite(engine: Engine, *, persistent: bool) -> None:
    @event.listens_for(engine, "connect")
    def configure_connection(
        dbapi_connection: sqlite3.Connection,
        _connection_record: object,
    ) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        if persistent:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def _migrate_legacy_schema(engine: Engine) -> None:
    """Add repository payload columns to databases created by migration 0001."""
    additions = {
        "memory_record": {
            "vector_pk": "INTEGER",
            "record_json": "JSON NOT NULL DEFAULT '{}'",
        },
        "idempotency_record": {
            "user_id": "VARCHAR NOT NULL DEFAULT 'legacy'",
            "fingerprint": "VARCHAR NOT NULL DEFAULT 'legacy'",
            "response_json": "JSON NOT NULL DEFAULT '{}'",
        },
        "audit_log": {
            "user_id": "VARCHAR NOT NULL DEFAULT 'system'",
            "metadata_json": "JSON NOT NULL DEFAULT '{}'",
        },
    }

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, columns in additions.items():
            existing = {
                column["name"]
                for column in inspector.get_columns(table_name)
            }
            for column_name, declaration in columns.items():
                if column_name not in existing:
                    connection.execute(
                        text(
                            f"ALTER TABLE {table_name} "
                            f"ADD COLUMN {column_name} {declaration}"
                        )
                    )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "ix_memory_record_vector_pk "
                "ON memory_record (vector_pk)"
            )
        )
