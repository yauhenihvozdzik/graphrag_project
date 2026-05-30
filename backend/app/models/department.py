"""Department model for GraphRAG platform."""

from typing import TYPE_CHECKING, List, Optional

from sqlmodel import Field, Relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.user import User


class Department(BaseModel, table=True):
    """Organizational department for access scoping.

    Attributes:
        id: Primary key (auto-increment).
        name: Display name (e.g., 'Юридический').
        code: Unique code used in RBAC (e.g., 'legal').
        description: Optional description.
        users: Related users in this department.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(unique=True, index=True)
    code: str = Field(unique=True, index=True)
    description: Optional[str] = Field(default=None)