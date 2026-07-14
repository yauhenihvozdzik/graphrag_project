"""Initial schema migration — GraphRAG Platform

Revision ID: 001
Revises: None
Create Date: 2026-06-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all initial tables for GraphRAG platform."""

    # ── User ──
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("role", sa.String(), nullable=False, server_default="viewer"),
        sa.Column("department", sa.String(), nullable=False, server_default="all"),
        sa.Column("clearance_level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("(now() at time zone 'utc')")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)

    # ── Department ──
    op.create_table(
        "department",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("code", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("(now() at time zone 'utc')")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_department_name"), "department", ["name"], unique=True)
    op.create_index(op.f("ix_department_code"), "department", ["code"], unique=True)

    # ── FileMetadata ──
    op.create_table(
        "filemetadata",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("file_modified", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_id", sa.String(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("(now() at time zone 'utc')")),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("(now() at time zone 'utc')")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_filemetadata_document_id"), "filemetadata", ["document_id"])

    # ── ChatSession ──
    op.create_table(
        "chat_session",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False, server_default=""),
        sa.Column("username", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("(now() at time zone 'utc')")),
        sa.PrimaryKeyConstraint("id"),
    )

    # ── ChatMessage ──
    op.create_table(
        "chat_message",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.String(), nullable=False, server_default="default"),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.String(length=10000), nullable=False),
        sa.Column("sources", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False,
                  server_default=sa.text("(now() at time zone 'utc')")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chatmessage_user_id"), "chat_message", ["user_id"])
    op.create_index(op.f("ix_chatmessage_session_id"), "chat_message", ["session_id"])


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_index(op.f("ix_chatmessage_session_id"), table_name="chat_message")
    op.drop_index(op.f("ix_chatmessage_user_id"), table_name="chat_message")
    op.drop_table("chat_message")
    op.drop_table("chat_session")
    op.drop_index(op.f("ix_filemetadata_document_id"), table_name="filemetadata")
    op.drop_table("filemetadata")
    op.drop_index(op.f("ix_department_code"), table_name="department")
    op.drop_index(op.f("ix_department_name"), table_name="department")
    op.drop_table("department")
    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_table("user")