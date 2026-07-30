"""Initial SQLAlchemy 2.0 schema for contracts 1.0.0."""

from sqlalchemy import Engine

from app.models import Base

revision = "0001"
down_revision = None


def upgrade(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def downgrade(engine: Engine) -> None:
    Base.metadata.drop_all(engine)
