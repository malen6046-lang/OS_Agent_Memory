"""ORM persistence model for audit entries."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, utc_now


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    audit_id: Mapped[str] = mapped_column(String, primary_key=True)
    operation: Mapped[str] = mapped_column(String, nullable=False, index=True)
    operator: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        default="system",
    )
    request_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    metadata_json: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
