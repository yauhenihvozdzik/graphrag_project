"""Chat session model for GraphRAG platform."""

from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class ChatSession(BaseModel, table=True):
    """Chat session model.

    Attributes:
        id: Session UUID (primary key).
        user_id: Foreign key to User.
        name: Session display name.
        username: Copied from user at creation time.
        user: Relationship to session owner.
    """

    __tablename__ = "chat_session"

    id: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id")
    name: str = Field(default="")
    username: Optional[str] = Field(default=None)
    user: "User" = Relationship(back_populates="sessions")
