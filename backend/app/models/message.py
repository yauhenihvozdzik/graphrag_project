"""Chat message model for persisting conversation history."""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class ChatMessage(SQLModel, table=True):
    """Persisted chat message."""

    __tablename__ = "chat_message"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    session_id: str = Field(default="default", index=True)
    role: str = Field(max_length=20)
    content: str = Field(max_length=10000)
    sources: Optional[str] = Field(default=None)  # JSON string of sources
    created_at: datetime = Field(default_factory=datetime.utcnow)