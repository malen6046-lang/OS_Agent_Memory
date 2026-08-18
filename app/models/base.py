"""Shared SQLAlchemy declarative base and timestamp helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import MetaData, String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator[datetime]):
    """Persist aware datetimes as normalized UTC ISO-8601 text in SQLite."""

    impl = String(35)
    cache_ok = True

    def process_bind_param(
        self,
        value: datetime | None,
        _dialect: Dialect,
    ) -> str | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must include timezone information")
        return value.astimezone(timezone.utc).isoformat()

    def process_result_value(
        self,
        value: str | datetime | None,
        _dialect: Dialect,
    ) -> datetime | None:
        if value is None:
            return None
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)


class Base(DeclarativeBase):
    """Base class for database models only."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    """UTC creation and update timestamps for domain persistence models."""

    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
