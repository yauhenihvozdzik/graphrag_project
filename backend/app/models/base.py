"""Base model with common fields."""

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


class BaseModel(SQLModel):
    """Base model with created_at timestamp."""

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
