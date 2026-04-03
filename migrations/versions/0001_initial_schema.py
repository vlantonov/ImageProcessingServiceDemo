"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-03 15:51:19.257967

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create images table with indexes."""
    op.create_table(
        "images",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("original_path", sa.Text(), nullable=False),
        sa.Column("thumbnail_path", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(20), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("channels", sa.Integer(), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_images_status", "images", ["status"])
    op.create_index("ix_images_created_at", "images", ["created_at"])
    op.create_index(
        "ix_images_expires_at",
        "images",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    """Drop images table."""
    op.drop_index("ix_images_expires_at", table_name="images")
    op.drop_index("ix_images_created_at", table_name="images")
    op.drop_index("ix_images_status", table_name="images")
    op.drop_table("images")
