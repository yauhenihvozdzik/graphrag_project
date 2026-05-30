"""User model for GraphRAG platform."""

from typing import TYPE_CHECKING, List, Optional

import bcrypt
from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.session import ChatSession


class User(BaseModel, table=True):
    """User model with role-based attributes.

    Attributes:
        id: Primary key.
        email: Unique email address.
        hashed_password: Bcrypt-hashed password.
        username: Optional display name.
        role: RBAC role (admin, analyst, viewer).
        department: Organizational department for access scoping.
        clearance_level: Security clearance (0=public, 3=secret).
        is_active: Whether the user account is active.
        sessions: Related chat sessions.
    """

    id: int = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    username: Optional[str] = Field(default=None)
    role: str = Field(default="viewer")
    department: str = Field(default="all")
    clearance_level: int = Field(default=0)
    is_active: bool = Field(default=False)
    sessions: List["ChatSession"] = Relationship(back_populates="user")

    def verify_password(self, password: str) -> bool:
        return bcrypt.checkpw(password.encode("utf-8"), self.hashed_password.encode("utf-8"))

    @staticmethod
    def hash_password(password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


# Avoid circular imports
from app.models.session import ChatSession  # noqa: E402