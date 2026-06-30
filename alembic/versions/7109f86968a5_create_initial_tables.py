"""create initial tables

Revision ID: 7109f86968a5
Revises:
Create Date: 2026-06-28 22:31:00.675581

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7109f86968a5"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("api_key", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_api_key"), "users", ["api_key"], unique=True)
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("short_code", sa.String(length=32), nullable=False),
        sa.Column("long_url", sa.String(length=2048), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_permanent", sa.Boolean(), nullable=False),
        sa.Column("click_count", sa.Integer(), nullable=False),
        sa.Column("webhook_url", sa.String(length=2048), nullable=True),
        sa.Column("webhook_threshold", sa.Integer(), nullable=True),
        sa.Column("webhook_fired", sa.Boolean(), nullable=False),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_links_expires_at"), "links", ["expires_at"], unique=False)
    op.create_index(op.f("ix_links_short_code"), "links", ["short_code"], unique=True)
    op.create_index(op.f("ix_links_user_id"), "links", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_links_user_id"), table_name="links")
    op.drop_index(op.f("ix_links_short_code"), table_name="links")
    op.drop_index(op.f("ix_links_expires_at"), table_name="links")
    op.drop_table("links")

    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_index(op.f("ix_users_api_key"), table_name="users")
    op.drop_table("users")
