"""SQLAlchemy models for dynamic admin settings management.

Tables:
    - admin_settings: current active key-value settings grouped by category
    - admin_settings_version: version grouping for audit trail
    - admin_settings_audit: change history with before/after values
"""

from datetime import UTC, datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from app.models.base import BaseModel


class AdminSetting(BaseModel, table=True):
    """Current active admin setting — flat key-value with category grouping.

    Attributes:
        id: Primary key, auto-increment.
        category: Setting category (prompts, llm_temperature, guardrails, …).
        key: Unique key within a category (e.g. 'system_prompt', 'temperature_chat').
        value: JSON-serialized value (string, number, list, dict).
        description: Optional human-readable description.
        is_active: Whether this setting is active. Default True.
        version_id: FK to admin_settings_version; tracks the version group.
        updated_at: Timestamp of last update.
        updated_by: FK to user who last updated this setting.
    """

    __tablename__ = "admin_settings"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("category", "key", name="uq_admin_settings_category_key"),
    )

    id: int = Field(default=None, primary_key=True)
    category: str = Field(max_length=64, index=True)
    key: str = Field(max_length=128)
    value: str = Field(default="")
    description: Optional[str] = Field(default=None)
    is_active: bool = Field(default=True)
    version_id: Optional[int] = Field(
        default=None, foreign_key="admin_settings_version.id", sa_column_kwargs={"nullable": True}
    )
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_by: Optional[int] = Field(
        default=None, foreign_key="user.id", sa_column_kwargs={"nullable": True}
    )


class AdminSettingsVersion(BaseModel, table=True):
    """Version grouping for admin settings audit trail.

    Each batch of setting changes creates a new version, allowing rollback
    and grouped history viewing.

    Attributes:
        id: Primary key, auto-increment.
        version_number: Human-readable version label (e.g. '1.0', '1.1').
        description: Optional notes describing this version's changes.
        created_by: FK to user who created this version.
        is_applied: Whether this version was applied (default False).
        audits: Related audit records.
    """

    __tablename__ = "admin_settings_version"  # type: ignore[assignment]

    id: int = Field(default=None, primary_key=True)
    version_number: str = Field(max_length=32)
    description: Optional[str] = Field(default=None)
    created_by: Optional[int] = Field(
        default=None, foreign_key="user.id", sa_column_kwargs={"nullable": True}
    )
    is_applied: bool = Field(default=False)
    audits: list["AdminSettingsAudit"] = Relationship(back_populates="version")


class AdminSettingsAudit(SQLModel, table=True):
    """Individual setting change record for audit trail.

    Captures the old and new values of a setting when updated, along with
    who made the change and why.

    NOTE: Inherits from SQLModel directly (not BaseModel) because the
    migration (002_admin_settings.py) does not include a ``created_at``
    column in the ``admin_settings_audit`` table. The ``changed_at``
    field serves the same purpose.

    Attributes:
        id: Primary key, auto-increment.
        setting_id: FK to the admin_settings record that was changed.
        old_value: Previous value (JSON-serialized).
        new_value: New value (JSON-serialized).
        changed_by: FK to user who made the change.
        changed_at: Timestamp of the change.
        change_reason: Optional reason for the change.
        version_id: FK to admin_settings_version (nullable).
        version: Relationship to AdminSettingsVersion.
    """

    __tablename__ = "admin_settings_audit"  # type: ignore[assignment]

    id: int = Field(default=None, primary_key=True)
    setting_id: int = Field(foreign_key="admin_settings.id", index=True)
    old_value: Optional[str] = Field(default=None)
    new_value: Optional[str] = Field(default=None)
    changed_by: Optional[int] = Field(
        default=None, foreign_key="user.id", sa_column_kwargs={"nullable": True}
    )
    changed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    change_reason: Optional[str] = Field(default=None)
    version_id: Optional[int] = Field(
        default=None, foreign_key="admin_settings_version.id", sa_column_kwargs={"nullable": True}
    )
    version: Optional["AdminSettingsVersion"] = Relationship(back_populates="audits")
