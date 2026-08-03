"""Fix: add missing created_at column to admin_settings_audit

Revision ID: 003
Revises: 002
Create Date: 2026-08-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add created_at column to admin_settings_audit table."""
    op.add_column(
        "admin_settings_audit",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=True,
            server_default=sa.text("(now() at time zone 'utc')"),
        ),
    )


def downgrade() -> None:
    """Remove created_at column from admin_settings_audit table."""
    op.drop_column("admin_settings_audit", "created_at")
