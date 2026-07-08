"""Base model with common fields."""

from datetime import UTC, datetime

from sqlalchemy.orm import declarative_base
from sqlmodel import Field, SQLModel

# SQLAlchemy declarative base for raw SQLAlchemy models (audit_logs, rbac_policies, etc.)
Base = declarative_base()


class BaseModel(SQLModel):
    """Base model with created_at timestamp."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
