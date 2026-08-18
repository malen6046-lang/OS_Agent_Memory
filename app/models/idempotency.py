"""ORM persistence model for idempotency records."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utc_now


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_record"

    idempotency_key: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        default="legacy",
    )
    operation: Mapped[str] = mapped_column(String, nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="legacy",
    )
    response_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
