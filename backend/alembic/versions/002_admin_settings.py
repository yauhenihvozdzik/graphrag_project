"""Add admin_settings tables for dynamic configuration

Revision ID: 002
Revises: 001
Create Date: 2026-07-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create admin_settings, admin_settings_version, admin_settings_audit tables
    and seed with current hardcoded default values."""

    # ── admin_settings_version: version grouping ──
    op.create_table(
        "admin_settings_version",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("version_number", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column("is_applied", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── admin_settings: current active settings ──
    op.create_table(
        "admin_settings",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "version_id", sa.Integer(), sa.ForeignKey("admin_settings_version.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category", "key", name="uq_admin_settings_category_key"),
    )
    op.create_index(op.f("ix_admin_settings_category"), "admin_settings", ["category"])
    op.create_index(op.f("ix_admin_settings_key"), "admin_settings", ["key"])

    # ── admin_settings_audit: change history ──
    op.create_table(
        "admin_settings_audit",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column(
            "setting_id", sa.Integer(), sa.ForeignKey("admin_settings.id"),
            nullable=False,
        ),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("changed_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
        sa.Column(
            "changed_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column(
            "version_id", sa.Integer(), sa.ForeignKey("admin_settings_version.id"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_admin_settings_audit_setting_id"), "admin_settings_audit", ["setting_id"],
    )
    op.create_index(
        op.f("ix_admin_settings_audit_changed_at"), "admin_settings_audit",
        [sa.text("changed_at DESC")],
    )

def downgrade() -> None:
    """Drop admin_settings tables in reverse dependency order."""
    op.drop_index(
        op.f("ix_admin_settings_audit_changed_at"), table_name="admin_settings_audit",
    )
    op.drop_index(
        op.f("ix_admin_settings_audit_setting_id"), table_name="admin_settings_audit",
    )
    op.drop_table("admin_settings_audit")
    op.drop_index(op.f("ix_admin_settings_key"), table_name="admin_settings")
    op.drop_index(op.f("ix_admin_settings_category"), table_name="admin_settings")
    op.drop_table("admin_settings")
    op.drop_table("admin_settings_version")
