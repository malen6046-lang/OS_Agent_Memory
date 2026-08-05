"""SQLite initialization, session creation, and transaction boundaries."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from threading import Lock

from sqlalchemy import Engine, URL, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base

from .config import ConfigManager

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_initialization_lock = Lock()


def create_sqlite_engine(
    database_url: str | URL, *, echo: bool = False
) -> Engine:
    url = make_url(database_url) if isinstance(database_url, str) else database_url
    if not url.drivername.startswith("sqlite"):
        raise ValueError("only SQLite database URLs are supported")

    _ensure_database_directory(url)
    engine = create_engine(
        url,
        echo=echo,
        future=True,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
    )
    _configure_sqlite(engine, persistent=url.database not in {None, ":memory:"})
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
        autoflush=False,
    )


class SqlAlchemyUnitOfWork:
    """Commit on success and roll back on every exception."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self.session: Session | None = None

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        assert self.session is not None
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
            self.session = None
        return False


@contextmanager
def session_scope(
    session_factory: sessionmaker[Session],
) -> Iterator[Session]:
    with SqlAlchemyUnitOfWork(session_factory) as unit_of_work:
        assert unit_of_work.session is not None
        yield unit_of_work.session


def init_db(database_url: str | Path | URL | None = None) -> Engine:
    """Initialize SQLite and create every registered ORM table."""

    global _engine, _session_factory
    with _initialization_lock:
        url = _coerce_sqlite_url(database_url) if database_url is not None else _default_url()
        engine = create_sqlite_engine(url)
        try:
            Base.metadata.create_all(engine)
        except Exception:
            engine.dispose()
            raise

        previous_engine = _engine
        _engine = engine
        _session_factory = create_session_factory(engine)
        if previous_engine is not None and previous_engine is not engine:
            previous_engine.dispose()
        return engine


def get_session() -> Session:
    if _session_factory is None:
        init_db()
    if _session_factory is None:  # pragma: no cover
        raise RuntimeError("database session factory was not initialized")
    return _session_factory()


def _default_url() -> URL:
    manager = ConfigManager()
    config = manager.load()
    data_dir = config.storage.data_dir.expanduser()
    if not data_dir.is_absolute():
        data_dir = manager.config_dir.parent / data_dir
    return URL.create(
        "sqlite",
        database=str((data_dir / config.storage.sqlite_file).resolve()),
    )


def _coerce_sqlite_url(database_url: str | Path | URL) -> URL:
    if isinstance(database_url, URL):
        return database_url
    if isinstance(database_url, Path):
        return URL.create("sqlite", database=str(database_url.expanduser().resolve()))
    if "://" not in database_url:
        return URL.create(
            "sqlite", database=str(Path(database_url).expanduser().resolve())
        )
    return make_url(database_url)


def _ensure_database_directory(url: URL) -> None:
    if url.database in {None, ":memory:"}:
        return
    Path(url.database).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


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
